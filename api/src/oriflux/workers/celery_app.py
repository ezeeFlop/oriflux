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
from oriflux.workers.anomaly_job import run_detection
from oriflux.workers.digest_job import run_digests
from oriflux.workers.export_job import run_exports
from oriflux.workers.geoip_refresh import RETRY_INTERVAL_S, maybe_refresh_geoip


def _refresh_geoip_job() -> bool:
    settings = get_settings()
    return maybe_refresh_geoip(settings, alert=partial(ops_alert, settings))


def _detect_anomalies_job() -> int:
    settings = get_settings()
    clickhouse = wait_for_clickhouse(settings)

    async def _run() -> int:
        engine = create_engine(settings)
        try:
            return await run_detection(
                create_session_factory(engine),
                ClickHouseExecutor(clickhouse),
                now=datetime.now(tz=UTC),
            )
        finally:
            await engine.dispose()

    detections = asyncio.run(_run())
    if detections:
        ops_alert(settings, f"anomaly detection: {detections} new deviation(s) recorded")
    return detections


def _send_digests_job() -> int:
    settings = get_settings()
    if not settings.resend_api_key:
        return 0  # email channel disabled (documented in config)
    clickhouse = wait_for_clickhouse(settings)

    def send(to: str, subject: str, body: str) -> None:
        import requests

        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.alert_email_from,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=30,
        )
        response.raise_for_status()

    async def _run() -> int:
        engine = create_engine(settings)
        try:
            return await run_digests(
                create_session_factory(engine),
                ClickHouseExecutor(clickhouse),
                send,
                now=datetime.now(tz=UTC),
            )
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 — alert, never crash the worker
        ops_alert(settings, f"digest send FAILED: {exc}")
        return 0


def _run_exports_job() -> int:
    settings = get_settings()
    if not settings.minio_url:
        return 0  # scheduled dumps disabled (documented in config)
    import io as _io

    from minio import Minio

    endpoint = settings.minio_url.replace("http://", "").replace("https://", "")
    client = Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_url.startswith("https"),
    )
    if not client.bucket_exists(settings.minio_export_bucket):
        client.make_bucket(settings.minio_export_bucket)

    def write_object(path: str, payload: bytes) -> None:
        client.put_object(
            settings.minio_export_bucket, path, _io.BytesIO(payload), len(payload),
            content_type="text/csv",
        )

    clickhouse = wait_for_clickhouse(settings)

    async def _run() -> int:
        engine = create_engine(settings)
        try:
            return await run_exports(
                create_session_factory(engine),
                ClickHouseExecutor(clickhouse),
                write_object,
                now=datetime.now(tz=UTC),
            )
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 — alert, never crash the worker
        ops_alert(settings, f"scheduled export FAILED: {exc}")
        return 0


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
            "detect-anomalies": {"task": "oriflux.detect_anomalies", "schedule": 3600},
            "send-digests": {"task": "oriflux.send_digests", "schedule": 3600},
            "run-exports": {"task": "oriflux.run_exports", "schedule": 24 * 3600},
        },
    )
    celery.task(name="oriflux.geoip_refresh")(_refresh_geoip_job)
    celery.task(name="oriflux.evaluate_alerts")(_evaluate_alerts_job)
    celery.task(name="oriflux.detect_anomalies")(_detect_anomalies_job)
    celery.task(name="oriflux.send_digests")(_send_digests_job)
    celery.task(name="oriflux.run_exports")(_run_exports_job)
    return celery


@worker_ready.connect
def kick_startup_jobs(sender: Any, **_: Any) -> None:
    # A cold start (empty geoip volume) must not wait for the first 6 h
    # beat tick; maybe_refresh_geoip makes the immediate run free when the
    # databases are already fresh.
    sender.app.send_task("oriflux.geoip_refresh")


app = create_celery(get_settings())
