"""Hourly anomaly-detection job (issue #27) — Celery beat entrypoint logic.

For every project of every non-muted org, pull the hourly registry series
(28 days) for the watched metrics, fit the seasonal baseline on everything
BEFORE the last completed hour, score that hour, and persist detections
(idempotent per project × metric × hour). Alerting rides ops_alert; the
per-org notification channels arrive with the connector work.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.ai.explain import explain_movement
from oriflux.db.models import AnomalyEvent, Organization, Project
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.workers.anomalies import Baseline, score_deviation

logger = logging.getLogger(__name__)

WATCHED_METRICS = ("pageviews", "api_requests")
HISTORY_DAYS = 28


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


def _hourly_series(
    executor: QueryExecutor, org_id: str, project_id: str, metric: str, now: datetime
) -> list[tuple[datetime, float]]:
    request = QueryRequest.model_validate(
        {
            "metric": metric,
            "granularity": "hour",
            "filters": [{"dimension": "project_id", "op": "eq", "value": project_id}],
            "period": {"start": now - timedelta(days=HISTORY_DAYS), "end": now},
        }
    )
    sql, params = build_query(request, org_id=org_id)
    series: list[tuple[datetime, float]] = []
    for row in executor.execute(sql, params):
        bucket = row.get("bucket")
        if bucket is None:
            continue
        ts = bucket if isinstance(bucket, datetime) else datetime.fromisoformat(str(bucket))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        series.append((ts, float(row.get("value") or 0.0)))
    return series


async def run_detection(
    session_factory: async_sessionmaker[AsyncSession],
    executor: QueryExecutor,
    *,
    now: datetime,
    gateway: Any | None = None,
) -> int:
    """Score the last completed hour for every project; returns detections."""
    window_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    detections = 0
    async with session_factory() as session:
        # snapshot plain values: ORM instances expire on the rollback below,
        # and a lazy refresh outside the greenlet context raises MissingGreenlet
        projects = [
            (row.org_id, row.id, row.slug)
            for row in (
                await session.execute(
                    select(Project.org_id, Project.id, Project.slug)
                    .join(Organization, Project.org_id == Organization.id)
                    .where(Organization.anomalies_muted.is_(False))
                )
            ).all()
        ]
        for org_id, project_id, slug in projects:
            for metric in WATCHED_METRICS:
                series = _hourly_series(
                    executor, str(org_id), str(project_id), metric, now
                )
                observed = next(
                    (value for ts, value in series if ts == window_start), None
                )
                if observed is None:
                    continue
                history = [(ts, value) for ts, value in series if ts < window_start]
                detection = score_deviation(observed, Baseline.fit(history), window_start)
                if detection is None:
                    continue
                explanation = ""
                if gateway is not None:
                    explanation = await explain_movement(
                        gateway, executor, org_id=str(org_id), project_id=str(project_id),
                        metric=metric, window=(window_start, window_start + timedelta(hours=1)),
                        headline=(
                            f"{metric} {detection.direction} {detection.deviation_pct:+.1f}% "
                            f"({detection.observed} vs expected {detection.expected})"
                        ),
                    )
                session.add(
                    AnomalyEvent(
                        org_id=org_id,
                        project_id=project_id,
                        metric=metric,
                        direction=detection.direction,
                        expected=detection.expected,
                        observed=detection.observed,
                        deviation_pct=detection.deviation_pct,
                        window_start=window_start,
                        explanation=explanation[:1024],
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:  # already recorded for this hour
                    await session.rollback()
                    continue
                detections += 1
                logger.info(
                    "anomaly: %s %s %s %+0.1f%% (expected %.1f, observed %.1f)",
                    slug, metric, detection.direction,
                    detection.deviation_pct, detection.expected, detection.observed,
                )
    return detections
