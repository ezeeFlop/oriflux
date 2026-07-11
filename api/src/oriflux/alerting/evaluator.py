"""Threshold-rule evaluation (issue #11; Celery since #16).

Runs as a 60 s Celery beat task (oriflux.workers.celery_app), which
resolved the asyncio deviation noted on #11. The evaluation path is the
point and it is registry-only: rule → typed QueryRequest →
build_query → executor. Never bespoke SQL.

State machine per rule:
  breach, no open event   → create alert_event, notify "firing" (once)
  breach, open event      → silent (dedup while the breach persists)
  no breach, open event   → resolve the event, notify "resolved" (once)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import AlertCondition, AlertEvent, AlertRule
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest

logger = logging.getLogger(__name__)

EVALUATION_INTERVAL_S = 60


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class Notifier(Protocol):
    def notify(self, rule: AlertRule, *, kind: str, value: float, extra: str = "") -> None: ...


class Evaluator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        executor: QueryExecutor,
        notifier: Notifier,
        explainer: Any = None,  # async (rule, value, now) -> str — optional (#36)
    ) -> None:
        self._session_factory = session_factory
        self._executor = executor
        self._notifier = notifier
        self._explainer = explainer

    def _evaluate(self, rule: AlertRule, now: datetime) -> float:
        request = QueryRequest.model_validate(
            {
                "metric": rule.metric,
                "filters": rule.filters,
                "period": {
                    "start": now - timedelta(minutes=rule.window_minutes),
                    "end": now,
                },
            }
        )
        sql, params = build_query(request, org_id=str(rule.org_id))
        rows = self._executor.execute(sql, params)
        value = rows[0]["value"] if rows else None
        return float(value) if value is not None else 0.0

    def _notify(self, rule: AlertRule, kind: str, value: float, extra: str = "") -> None:
        try:
            self._notifier.notify(rule, kind=kind, value=value, extra=extra)
        except Exception:  # noqa: BLE001 — notification failure must not stop evaluation
            logger.exception("alert notification failed (rule %s, %s)", rule.id, kind)

    async def run_once(self, *, now: datetime) -> None:
        async with self._session_factory() as session:
            rules = (
                (await session.execute(select(AlertRule).where(AlertRule.enabled)))
                .scalars()
                .all()
            )
            for rule in rules:
                try:
                    value = await asyncio.to_thread(self._evaluate, rule, now)
                except Exception:  # noqa: BLE001 — one bad rule must not stop the rest
                    logger.exception("evaluation failed for rule %s", rule.id)
                    continue

                open_event = (
                    await session.execute(
                        select(AlertEvent).where(
                            AlertEvent.rule_id == rule.id,
                            AlertEvent.resolved_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                breached = (
                    value > rule.threshold
                    if rule.condition == AlertCondition.gt
                    else value < rule.threshold
                )

                if breached and open_event is None:
                    session.add(
                        AlertEvent(rule_id=rule.id, org_id=rule.org_id, value=value,
                                   fired_at=now)
                    )
                    await session.commit()
                    extra = ""
                    if self._explainer is not None:
                        try:
                            extra = await self._explainer(rule, value, now)
                        except Exception:  # noqa: BLE001 — optional
                            extra = ""
                    await asyncio.to_thread(self._notify, rule, "firing", value, extra)
                elif not breached and open_event is not None:
                    open_event.resolved_at = now
                    await session.commit()
                    await asyncio.to_thread(self._notify, rule, "resolved", value)
