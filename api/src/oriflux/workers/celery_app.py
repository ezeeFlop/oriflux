"""Celery foundation of oriflux_workers (issue #16, PRD §8.2).

Periodic jobs run as beat tasks: the GeoIP refresh (6 h tick, monthly
freshness handled by maybe_refresh_geoip) and the threshold-alert
evaluation (60 s) — closing the asyncio deviation noted on #11. The
Redis Streams → ClickHouse batchers deliberately stay asyncio tasks in
main.py: they are continuous consumers, not jobs. Phase-2 workloads
(digests, anomalies, connectors, exports) land on this app.

Footprint (NFR §11): one worker process with embedded beat
(`celery … worker --beat --concurrency 1`), no result backend.
"""

import asyncio
from datetime import UTC, datetime
from functools import partial
from typing import Any

from celery import Celery
from celery.signals import worker_ready

from oriflux.alerting.evaluator import EVALUATION_INTERVAL_S, Evaluator
from oriflux.alerting.notify import AlertNotifier
from oriflux.alerts import ops_alert
from oriflux.config import Settings, get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.logs import setup_logging
from oriflux.storage.clickhouse import ClickHouseExecutor, wait_for_clickhouse
from oriflux.workers.geoip_refresh import RETRY_INTERVAL_S, maybe_refresh_geoip


def _refresh_geoip_job() -> bool:
    settings = get_settings()
    return maybe_refresh_geoip(settings, alert=partial(ops_alert, settings))


def _evaluate_alerts_job() -> None:
    settings = get_settings()
    clickhouse = wait_for_clickhouse(settings)

    async def _run() -> None:
        engine = create_engine(settings)
        try:
            evaluator = Evaluator(
                create_session_factory(engine),
                ClickHouseExecutor(clickhouse),
                AlertNotifier(settings),
            )
            await evaluator.run_once(now=datetime.now(tz=UTC))
        finally:
            await engine.dispose()

    asyncio.run(_run())


def create_celery(settings: Settings) -> Celery:
    setup_logging()
    celery = Celery("oriflux", broker=settings.redis_url)
    celery.conf.update(
        timezone="UTC",
        broker_connection_retry_on_startup=True,
        task_ignore_result=True,
        worker_concurrency=1,
        worker_prefetch_multiplier=1,
        beat_schedule={
            "geoip-refresh": {"task": "oriflux.geoip_refresh", "schedule": RETRY_INTERVAL_S},
            "evaluate-alerts": {
                "task": "oriflux.evaluate_alerts",
                "schedule": EVALUATION_INTERVAL_S,
            },
        },
    )
    celery.task(name="oriflux.geoip_refresh")(_refresh_geoip_job)
    celery.task(name="oriflux.evaluate_alerts")(_evaluate_alerts_job)
    return celery


@worker_ready.connect
def kick_startup_jobs(sender: Any, **_: Any) -> None:
    # A cold start (empty geoip volume) must not wait for the first 6 h
    # beat tick; maybe_refresh_geoip makes the immediate run free when the
    # databases are already fresh.
    sender.app.send_task("oriflux.geoip_refresh")


app = create_celery(get_settings())
