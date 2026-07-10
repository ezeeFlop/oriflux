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

from oriflux.alerts import ops_alert
from oriflux.config import Settings, get_settings
from oriflux.storage.clickhouse import ClickHouseSink, ensure_schema, wait_for_clickhouse
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
        batcher = Batcher(
            redis,
            ClickHouseSink(clickhouse),
            consumer=socket.gethostname(),
            batch_size=settings.batch_size,
            block_ms=settings.batch_block_ms,
        )
        tasks = [
            asyncio.create_task(batcher.run_forever()),
            asyncio.create_task(run_geoip_refresh_forever(settings)),
        ]
        yield
        for task in tasks:
            task.cancel()
        await redis.aclose()

    app = FastAPI(title="oriflux_workers", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
