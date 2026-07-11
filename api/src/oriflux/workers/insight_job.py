"""Daily insights job (issue #35): registry numbers → pure findings →
SPT Models writes the prose (optional — the numbers ARE the insight)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import Insight, Organization, Project
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.workers.insights import detect_findings

logger = logging.getLogger(__name__)

WATCHED = ("visitors", "pageviews", "api_requests", "custom_events")


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class ChatGateway(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def chat(self, org_id: str, *, feature: str, messages: list[dict[str, str]],
                   temperature: float = 0.2) -> str: ...


def _scalar(executor: QueryExecutor, metric: str, org_id: str, project_id: str,
            start: datetime, end: datetime) -> tuple[float, dict[str, Any]]:
    request = QueryRequest.model_validate({
        "metric": metric,
        "filters": [{"dimension": "project_id", "op": "eq", "value": project_id}],
        "period": {"start": start, "end": end},
    })
    sql, params = build_query(request, org_id=org_id)
    rows = executor.execute(sql, params)
    value = rows[0].get("value") if rows else 0
    return float(value or 0), request.model_dump(mode="json")


async def run_insights(
    session_factory: async_sessionmaker[AsyncSession],
    executor: QueryExecutor,
    gateway: ChatGateway,
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(tz=UTC)
    day = now.date().isoformat()
    week_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = week_end - timedelta(days=7)
    prev_start = week_start - timedelta(days=7)
    created = 0
    async with session_factory() as session:
        projects = [
            (row.org_id, row.id, row.name)
            for row in (
                await session.execute(
                    select(Project.org_id, Project.id, Project.name).join(
                        Organization, Project.org_id == Organization.id
                    )
                )
            ).all()
        ]
        for org_id, project_id, project_name in projects:
            metrics: dict[str, tuple[float, float]] = {}
            queries: dict[str, dict[str, Any]] = {}
            for metric in WATCHED:
                current, query = _scalar(
                    executor, metric, str(org_id), str(project_id), week_start, week_end
                )
                previous, _ = _scalar(
                    executor, metric, str(org_id), str(project_id), prev_start, week_start
                )
                metrics[metric] = (current, previous)
                queries[metric] = query
            for finding in detect_findings(metrics):
                numbers = {
                    "current": finding.current,
                    "previous": finding.previous,
                    "delta_pct": finding.delta_pct,
                    "window": "7d vs previous 7d",
                }
                text = ""
                if getattr(gateway, "enabled", False):
                    try:
                        text = await gateway.chat(
                            str(org_id),
                            feature="insights",
                            messages=[
                                {"role": "system", "content": (
                                    "Write ONE short sentence (French) stating this analytics "
                                    "movement, citing only these numbers. No speculation."
                                )},
                                {"role": "user", "content": (
                                    f"project: {project_name}, metric: {finding.metric}, "
                                    f"numbers: {numbers}"
                                )},
                            ],
                        )
                    except Exception:  # noqa: BLE001 — prose is optional
                        text = ""
                session.add(
                    Insight(
                        org_id=org_id, project_id=project_id, day=day,
                        key=finding.key, kind=finding.kind, metric=finding.metric,
                        numbers=numbers, query=queries[finding.metric],
                        text=text, language="fr",
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    continue
                created += 1
                logger.info("insight: %s %s %+0.1f%%", project_name,
                            finding.metric, finding.delta_pct)
    return created
