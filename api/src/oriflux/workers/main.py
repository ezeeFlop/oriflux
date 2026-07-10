"""oriflux_workers — background processing entrypoint.

Runs the Redis Streams → ClickHouse batchers as asyncio tasks (they are
continuous consumers) next to a minimal FastAPI app so /healthz responds
like on the other services. Periodic jobs — GeoIP refresh, alert
evaluation, and the phase-2 workloads — live in the Celery app
(oriflux.workers.celery_app), launched as a sibling process by the
service entrypoint (issue #16).
"""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from oriflux.config import get_settings
from oriflux.logs import setup_logging
from oriflux.models.api_metrics import ApiMinuteRow
from oriflux.storage.clickhouse import (
    ApiMinutelySink,
    ClickHouseSink,
    ensure_schema,
    wait_for_clickhouse,
)
from oriflux.storage.redis_stream import API_CONSUMER_GROUP, API_METRICS_STREAM
from oriflux.workers.batcher import Batcher


def create_app() -> FastAPI:
    setup_logging()
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
        tasks = [
            asyncio.create_task(events_batcher.run_forever()),
            asyncio.create_task(api_batcher.run_forever()),
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
