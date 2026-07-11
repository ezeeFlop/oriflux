"""Digest send job (issue #26) — assembles registry numbers, renders in the
subscriber's language, delivers via an injectable sender, and records each
send so a period can never go out twice."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import DigestSend, DigestSubscription, Project, User
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.workers.digests import due_period, render_digest

logger = logging.getLogger(__name__)

Sender = Callable[[str, str, str], None]  # (to, subject, body)


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


def _scalar(executor: QueryExecutor, metric: str, org_id: str, project_id: str,
            start: datetime, end: datetime) -> float:
    request = QueryRequest.model_validate({
        "metric": metric,
        "filters": [{"dimension": "project_id", "op": "eq", "value": project_id}],
        "period": {"start": start, "end": end},
    })
    sql, params = build_query(request, org_id=org_id)
    rows = executor.execute(sql, params)
    value = rows[0].get("value") if rows else 0
    return float(value or 0)


def _project_numbers(executor: QueryExecutor, org_id: str, project_id: str, name: str,
                     start: datetime, end: datetime) -> dict[str, object]:
    span = end - start
    prev_start, prev_end = start - span, start
    return {
        "project": name,
        "visitors": _scalar(executor, "visitors", org_id, project_id, start, end),
        "visitors_prev": _scalar(executor, "visitors", org_id, project_id, prev_start, prev_end),
        "pageviews": _scalar(executor, "pageviews", org_id, project_id, start, end),
        "pageviews_prev": _scalar(executor, "pageviews", org_id, project_id, prev_start, prev_end),
        "api_requests": _scalar(executor, "api_requests", org_id, project_id, start, end),
        "api_requests_prev": _scalar(
            executor, "api_requests", org_id, project_id, prev_start, prev_end
        ),
        "error_rate_5xx": _scalar(executor, "api_error_rate_5xx", org_id, project_id, start, end),
    }


def _period_bounds(cadence: str, now: datetime) -> tuple[datetime, datetime]:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if cadence == "weekly":
        return today - timedelta(days=7), today
    first_of_month = today.replace(day=1)
    prev_last = first_of_month - timedelta(days=1)
    return prev_last.replace(day=1), first_of_month


async def run_digests(
    session_factory: async_sessionmaker[AsyncSession],
    executor: QueryExecutor,
    sender: Sender,
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(tz=UTC)
    sent = 0
    async with session_factory() as session:
        subscriptions = [
            (row.id, row.org_id, row.cadence, row.language, row.email)
            for row in (
                await session.execute(
                    select(
                        DigestSubscription.id,
                        DigestSubscription.org_id,
                        DigestSubscription.cadence,
                        DigestSubscription.language,
                        User.email,
                    ).join(User, DigestSubscription.user_id == User.id)
                )
            ).all()
        ]
        for sub_id, org_id, cadence, language, email in subscriptions:
            period_key = due_period(cadence, now)
            if period_key is None:
                continue
            already = await session.execute(
                select(DigestSend).where(
                    DigestSend.subscription_id == sub_id,
                    DigestSend.period_key == period_key,
                )
            )
            if already.scalar_one_or_none() is not None:
                continue
            projects = [
                (row.id, row.name)
                for row in (
                    await session.execute(
                        select(Project.id, Project.name).where(Project.org_id == org_id)
                    )
                ).all()
            ]
            start, end = _period_bounds(cadence, now)
            numbers = [
                _project_numbers(executor, str(org_id), str(pid), name, start, end)
                for pid, name in projects
            ]
            subject, body = render_digest(numbers, language=language, period_label=period_key)
            sender(email, subject, body)
            session.add(DigestSend(subscription_id=sub_id, period_key=period_key))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                continue
            sent += 1
            logger.info("digest sent to %s (%s, %s)", email, cadence, period_key)
    return sent
