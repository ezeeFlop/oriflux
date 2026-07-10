"""Agent-facing analytics tools (PRD §7.1) — exposed over MCP by fastapi-mcp.

Every tool is a plain REST endpoint authenticated by a read-scoped API key
and compiled through the metric/dimension registry — the exact same
contract as the dashboard and /api/v1/query, so answers here can never
drift from what the UI shows. Read-only by design; annotate/insights/
alerts tools arrive in phase 3.

(The module is deliberately NOT named `mcp` — a subpackage of that name
shadows the mcp PyPI package fastapi-mcp depends on; see CLAUDE.md.)
"""

import asyncio
import uuid
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_session, require_read_key_org
from oriflux.db.models import Organization, Project
from oriflux.query.engine import build_query
from oriflux.query.models import Period, QueryRequest

router = APIRouter(prefix="/api/v1", tags=["tools"])


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


def _executor(request: Request) -> QueryExecutor:
    executor: QueryExecutor = request.app.state.query_executor()
    return executor


async def _project_id(session: AsyncSession, org_id: str, slug: str) -> str:
    org = (
        await session.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    ).scalar_one()
    project = (
        await session.execute(
            select(Project).where(Project.org_id == org.id, Project.slug == slug)
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"unknown project slug: {slug!r}")
    return str(project.id)


def _metric(
    executor: QueryExecutor,
    org_id: str,
    project_id: str,
    metric: str,
    period: Period,
    dimensions: list[str] | None = None,
) -> list[dict[str, Any]]:
    request = QueryRequest(
        metric=metric,
        dimensions=dimensions or [],
        filters=[{"dimension": "project_id", "op": "eq", "value": project_id}],  # type: ignore[list-item]
        period=period,
    )
    sql, params = build_query(request, org_id=org_id)
    return executor.execute(sql, params)


def _scalar(rows: list[dict[str, Any]]) -> Any:
    return rows[0]["value"] if rows else 0


class ProjectOut(BaseModel):
    id: str
    slug: str
    name: str


@router.get(
    "/projects",
    operation_id="list_projects",
    summary="List the projects (products) visible to this API key",
)
async def list_projects(
    org_id: str = Depends(require_read_key_org),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectOut]:
    projects = (
        (
            await session.execute(
                select(Project).where(Project.org_id == uuid.UUID(org_id)).order_by(Project.slug)
            )
        )
        .scalars()
        .all()
    )
    return [ProjectOut(id=str(p.id), slug=p.slug, name=p.name) for p in projects]


class OverviewIn(BaseModel):
    project: str  # slug
    period: Period


@router.post(
    "/overview",
    operation_id="get_overview",
    summary="Traffic/session/API-health synthesis for one project over a period",
)
async def get_overview(
    payload: OverviewIn,
    request: Request,
    org_id: str = Depends(require_read_key_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    project_id = await _project_id(session, org_id, payload.project)
    executor = _executor(request)

    def gather() -> dict[str, Any]:
        return {
            metric: _scalar(_metric(executor, org_id, project_id, metric, payload.period))
            for metric in (
                "visitors", "pageviews", "sessions", "bounce_rate", "session_duration",
                "api_requests", "api_error_rate_4xx", "api_error_rate_5xx", "api_latency_p95",
            )
        }

    numbers = await asyncio.to_thread(gather)
    return {
        "project": payload.project,
        "period": payload.period.model_dump(mode="json"),
        # multi-day visitor totals are visit-days (daily rotating hash, PRD §9)
        "visitors_note": "multi-day visitor totals count visit-days, not distinct people",
        **numbers,
    }


class GeoBreakdownIn(BaseModel):
    project: str
    level: Literal["country", "region", "city"] = "country"
    period: Period
    metric: Literal["visitors", "pageviews", "api_requests"] = "visitors"


@router.post(
    "/geo-breakdown",
    operation_id="get_geo_breakdown",
    summary="Geographic distribution (country/region/city) of a project's traffic",
)
async def get_geo_breakdown(
    payload: GeoBreakdownIn,
    request: Request,
    org_id: str = Depends(require_read_key_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if payload.metric == "api_requests" and payload.level != "country":
        raise HTTPException(
            status_code=422, detail="api_requests supports the 'country' level only"
        )
    project_id = await _project_id(session, org_id, payload.project)
    executor = _executor(request)
    rows = await asyncio.to_thread(
        _metric, executor, org_id, project_id, payload.metric, payload.period, [payload.level]
    )
    rows.sort(key=lambda r: r["value"], reverse=True)
    return {"project": payload.project, "level": payload.level, "rows": rows}


class ApiHealthIn(BaseModel):
    project: str
    period: Period


@router.post(
    "/api-health",
    operation_id="get_api_health",
    summary="API traffic, error rates, latency percentiles and top endpoints",
)
async def get_api_health(
    payload: ApiHealthIn,
    request: Request,
    org_id: str = Depends(require_read_key_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    project_id = await _project_id(session, org_id, payload.project)
    executor = _executor(request)

    def gather() -> dict[str, Any]:
        top_endpoints = _metric(
            executor, org_id, project_id, "api_requests", payload.period, ["endpoint"]
        )
        top_endpoints.sort(key=lambda r: r["value"], reverse=True)
        return {
            "requests": _scalar(
                _metric(executor, org_id, project_id, "api_requests", payload.period)
            ),
            "error_rate_4xx": _scalar(
                _metric(executor, org_id, project_id, "api_error_rate_4xx", payload.period)
            ),
            "error_rate_5xx": _scalar(
                _metric(executor, org_id, project_id, "api_error_rate_5xx", payload.period)
            ),
            "latency_p50_ms": _scalar(
                _metric(executor, org_id, project_id, "api_latency_p50", payload.period)
            ),
            "latency_p95_ms": _scalar(
                _metric(executor, org_id, project_id, "api_latency_p95", payload.period)
            ),
            "latency_p99_ms": _scalar(
                _metric(executor, org_id, project_id, "api_latency_p99", payload.period)
            ),
            "top_endpoints": top_endpoints[:10],
        }

    return {"project": payload.project, **(await asyncio.to_thread(gather))}
