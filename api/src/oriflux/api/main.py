"""oriflux_api — REST /api/v1 + query engine.

POST /api/v1/query is the one query surface: a typed query object compiled
through the registry (PRD §8.3). The response echoes the executed SQL for
auditability — the same property Ask Oriflux will rely on in phase 3.
"""

import asyncio
from typing import Any, Protocol

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from oriflux.auth import require_bearer_key
from oriflux.config import Settings, get_settings
from oriflux.query.engine import build_query
from oriflux.query.models import Period, QueryRequest


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class QueryResponse(BaseModel):
    metric: str
    period: Period
    results: list[dict[str, Any]]
    compare_results: list[dict[str, Any]] | None = None
    sql: str


def _previous_period(period: Period) -> Period:
    duration = period.end - period.start
    return Period(start=period.start - duration, end=period.start)


def create_app(executor: QueryExecutor | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="oriflux_api")

    def get_executor() -> QueryExecutor:
        if executor is not None:
            return executor
        from oriflux.storage.clickhouse import ClickHouseExecutor

        return ClickHouseExecutor.from_settings(settings)

    require_read_key = require_bearer_key(settings.read_api_key)

    @app.post("/api/v1/query", dependencies=[Depends(require_read_key)])
    async def query(
        request: QueryRequest, executor: QueryExecutor = Depends(get_executor)
    ) -> QueryResponse:
        sql, params = build_query(request, org_id=settings.org_id)
        results = await asyncio.to_thread(executor.execute, sql, params)

        compare_results = None
        if request.compare_to == "previous_period":
            previous = _previous_period(request.period)
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

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
