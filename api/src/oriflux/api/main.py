"""oriflux_api — REST /api/v1: auth, admin (tenancy), and the query engine.

POST /api/v1/query is the one query surface: a typed query object compiled
through the registry (PRD §8.3), authenticated by a read-scoped API key and
always scoped to that key's org (row-level isolation). The response echoes
the executed SQL for auditability — the same property Ask Oriflux will rely
on in phase 3.
"""

import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.ai.ask import AskCompilationError, compile_question
from oriflux.ai.gateway import AiBudgetExhausted, AiGateway
from oriflux.api import (
    admin,
    alerts,
    annotations,
    anomalies,
    auth,
    connectors,
    digest,
    goals,
    infra,
    tools,
)
from oriflux.api.deps import require_read_org
from oriflux.config import Settings, get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.db.migrate import run_migrations
from oriflux.logs import setup_logging
from oriflux.query.engine import build_query
from oriflux.query.funnel import FunnelRequest, build_funnel
from oriflux.query.models import Filter, Period, QueryRequest
from oriflux.query.retention import RetentionRequest, build_retention
from oriflux.security.google import GoogleVerifier, make_google_verifier


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class AskRequest(BaseModel):
    question: str
    project_id: str | None = None


class QueryResponse(BaseModel):
    metric: str
    period: Period
    results: list[dict[str, Any]]
    compare_results: list[dict[str, Any]] | None = None
    sql: str


def _comparison_period(period: Period, compare_to: str) -> Period:
    if compare_to == "previous_period":
        duration = period.end - period.start
        return Period(start=period.start - duration, end=period.start)

    # previous_year: same calendar dates one year earlier (Feb 29 → Feb 28)
    def one_year_back(moment: Any) -> Any:
        try:
            return moment.replace(year=moment.year - 1)
        except ValueError:
            return moment.replace(year=moment.year - 1, day=28)

    return Period(start=one_year_back(period.start), end=one_year_back(period.end))


def create_app(
    executor: QueryExecutor | None = None,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    google_verifier: GoogleVerifier | None = None,
    ai_gateway: AiGateway | None = None,
) -> FastAPI:
    setup_logging()
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if session_factory is None:
            await asyncio.to_thread(run_migrations, settings)
            engine = create_engine(settings)
            app.state.session_factory = create_session_factory(engine)
            yield
            await engine.dispose()
        else:
            yield

    app = FastAPI(title="oriflux_api", lifespan=lifespan)
    app.state.settings = settings
    app.state.google_verifier = google_verifier or make_google_verifier(
        settings.google_client_id
    )
    if session_factory is not None:
        app.state.session_factory = session_factory

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(tools.router)
    app.include_router(alerts.router)
    app.include_router(goals.router)
    app.include_router(annotations.router)
    app.include_router(anomalies.router)
    app.include_router(digest.router)
    app.include_router(connectors.router)
    app.include_router(infra.router)

    def get_executor() -> QueryExecutor:
        if executor is not None:
            return executor
        from oriflux.storage.clickhouse import ClickHouseExecutor

        return ClickHouseExecutor.from_settings(settings)

    app.state.query_executor = get_executor

    def get_ai_gateway() -> AiGateway:
        if ai_gateway is not None:
            return ai_gateway
        cached = getattr(app.state, "ai_gateway", None)
        if cached is None:
            cached = AiGateway(settings, app.state.session_factory)
            app.state.ai_gateway = cached
        return cached

    @app.post(
        "/api/v1/query",
        operation_id="query_metrics",
        summary="Run a typed analytics query (single contract: registry-validated)",
    )
    async def query(
        request: QueryRequest,
        org_id: str = Depends(require_read_org),
        executor: QueryExecutor = Depends(get_executor),
    ) -> QueryResponse:
        sql, params = build_query(request, org_id=org_id)
        results = await asyncio.to_thread(executor.execute, sql, params)

        compare_results = None
        if request.compare_to is not None:
            previous = _comparison_period(request.period, request.compare_to)
            compare_params: dict[str, Any] = {
                **params,
                "start": previous.start,
                "end": previous.end,
            }
            compare_results = await asyncio.to_thread(executor.execute, sql, compare_params)

        return QueryResponse(
            metric=request.metric,
            period=request.period,
            results=results,
            compare_results=compare_results,
            sql=sql,
        )

    @app.post(
        "/api/v1/funnel",
        operation_id="query_funnel",
        summary="Run a typed funnel query (windowFunnel; session-scoped or identified)",
    )
    async def funnel(
        request: FunnelRequest,
        org_id: str = Depends(require_read_org),
        executor: QueryExecutor = Depends(get_executor),
    ) -> dict[str, Any]:
        sql, params = build_funnel(request, org_id=org_id)
        rows = await asyncio.to_thread(executor.execute, sql, params)
        if request.segment_by is not None:
            return {"scope": request.scope, "segment_by": request.segment_by,
                    "segments": rows, "sql": sql}
        counts = rows[0] if rows else {}
        entered = [
            int(counts.get(f"step_{i + 1}", 0) or 0) for i in range(len(request.steps))
        ]
        steps = [
            {"step": i + 1, "target": step.target, "entered": entered[i]}
            for i, step in enumerate(request.steps)
        ]
        first, last = entered[0], entered[-1]
        return {
            "scope": request.scope,
            "steps": steps,
            "conversion_rate": 0.0 if first == 0 else round(100 * last / first, 1),
            "sql": sql,
        }

    @app.post(
        "/api/v1/retention",
        operation_id="query_retention",
        summary="Retention cohorts (identified users only, by design)",
    )
    async def retention(
        request: RetentionRequest,
        org_id: str = Depends(require_read_org),
        executor: QueryExecutor = Depends(get_executor),
    ) -> dict[str, Any]:
        sql, params = build_retention(request, org_id=org_id)
        rows = await asyncio.to_thread(executor.execute, sql, params)
        return {
            "granularity": request.granularity,
            "activation_event": request.activation_event,
            "cohorts": rows,
            "sql": sql,
        }

    @app.post(
        "/api/v1/export",
        operation_id="export_csv",
        summary="Export a typed registry query as CSV",
    )
    async def export_csv(
        request: QueryRequest,
        limit: int = 100_000,
        org_id: str = Depends(require_read_org),
        executor: QueryExecutor = Depends(get_executor),
    ) -> Response:
        sql, params = build_query(request, org_id=org_id)
        rows = await asyncio.to_thread(executor.execute, sql, params)
        rows = rows[: max(1, min(limit, 100_000))]  # hard cap (multi-tenancy quota)
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="oriflux-{request.metric}.csv"'
            },
        )

    @app.post(
        "/api/v1/ask",
        operation_id="ask_oriflux",
        summary="Natural-language analytics: compiles to the typed registry query (never SQL)",
    )
    async def ask(
        request: AskRequest,
        org_id: str = Depends(require_read_org),
        executor: QueryExecutor = Depends(get_executor),
        gateway: AiGateway = Depends(get_ai_gateway),
    ) -> dict[str, Any]:
        if not gateway.enabled:
            raise HTTPException(status_code=503, detail="AI is not configured")
        try:
            compiled = await compile_question(gateway, org_id, question=request.question)
        except AiBudgetExhausted as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except AskCompilationError as exc:
            raise HTTPException(
                status_code=422, detail=f"could not compile the question: {exc}"
            ) from exc
        if request.project_id:
            compiled.filters.append(
                Filter(dimension="project_id", op="eq", value=request.project_id)
            )
        sql, params = build_query(compiled, org_id=org_id)
        results = await asyncio.to_thread(executor.execute, sql, params)
        answer = ""
        try:
            answer = await gateway.chat(
                org_id,
                feature="ask",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer the analytics question in the question's language, in one or "
                            "two sentences, citing ONLY the numbers provided. Never invent values."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"question: {request.question}\n"
                            f"query: {compiled.model_dump_json()}\n"
                            f"results: {json.dumps(results[:50], default=str)}"
                        ),
                    },
                ],
            )
        except Exception:  # noqa: BLE001 — phrasing is optional; numbers are the answer
            answer = ""
        return {
            "question": request.question,
            "query": compiled.model_dump(mode="json"),
            "sql": sql,
            "results": results,
            "answer": answer,
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # MCP server (PRD §7.1): the same five read-only operations as REST,
    # served HTTP-streamable at /mcp. Auth rides on each endpoint's
    # read-key dependency — the client's Authorization header is forwarded.
    FastApiMCP(
        app,
        name="Oriflux Analytics",
        description=(
            "Read-only analytics for the Sponge Theory ecosystem: web traffic, "
            "sessions, geography and API health, queried through the typed "
            "metric registry. Requires a read-scoped API key (Bearer)."
        ),
        include_operations=[
            "list_projects",
            "get_overview",
            "query_metrics",
            "query_funnel",
            "query_retention",
            "get_geo_breakdown",
            "get_api_health",
            "get_insights",
            "get_alerts",
            "ask_oriflux",
            # the ONE write operation: requires the project's ingest key —
            # read keys are refused (403), the read-only default stays intact
            "annotate",
        ],
    ).mount_http()

    return app


app = create_app()
