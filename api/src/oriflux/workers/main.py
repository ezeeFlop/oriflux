"""oriflux_workers — background processing entrypoint.

For the walking skeleton this runs the Redis Streams → ClickHouse batcher
as an asyncio task next to a minimal FastAPI app (so /healthz responds like
on the other services). Celery (anomalies, insights, digests, webhooks)
replaces the naked loop when those workloads arrive.
"""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from redis.asyncio import Redis

from oriflux.alerting.evaluator import Evaluator
from oriflux.alerting.notify import AlertNotifier
from oriflux.alerts import ops_alert
from oriflux.config import Settings, get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.models.api_metrics import ApiMinuteRow
from oriflux.storage.clickhouse import (
    ApiMinutelySink,
    ClickHouseExecutor,
    ClickHouseSink,
    ensure_schema,
    wait_for_clickhouse,
)
from oriflux.storage.redis_stream import API_CONSUMER_GROUP, API_METRICS_STREAM
from oriflux.workers.batcher import Batcher
from oriflux.workers.geoip_refresh import REFRESH_INTERVAL_S, RETRY_INTERVAL_S, refresh_geoip


async def run_geoip_refresh_forever(settings: Settings) -> None:
    while True:
        refreshed = await asyncio.to_thread(
            refresh_geoip, settings, alert=partial(ops_alert, settings)
        )
        await asyncio.sleep(REFRESH_INTERVAL_S if refreshed else RETRY_INTERVAL_S)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        clickhouse = await asyncio.to_thread(wait_for_clickhouse, settings)
        await asyncio.to_thread(ensure_schema, clickhouse)
        redis = Redis.from_url(settings.redis_url)
        events_batcher = Batcher(
            redis,
            ClickHouseSink(clickhouse),
            consumer=socket.gethostname(),
            batch_size=settings.batch_size,
            block_ms=settings.batch_block_ms,
        )
        api_batcher = Batcher(
            redis,
            ApiMinutelySink(clickhouse),
            consumer=socket.gethostname(),
            batch_size=settings.batch_size,
            block_ms=settings.batch_block_ms,
            stream=API_METRICS_STREAM,
            group=API_CONSUMER_GROUP,
            model=ApiMinuteRow,
        )
        engine = create_engine(settings)
        evaluator = Evaluator(
            create_session_factory(engine),
            ClickHouseExecutor(clickhouse),
            AlertNotifier(settings),
        )
        tasks = [
            asyncio.create_task(events_batcher.run_forever()),
            asyncio.create_task(api_batcher.run_forever()),
            asyncio.create_task(run_geoip_refresh_forever(settings)),
            asyncio.create_task(evaluator.run_forever()),
        ]
        yield
        for task in tasks:
            task.cancel()
        await redis.aclose()
        await engine.dispose()

    app = FastAPI(title="oriflux_workers", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
