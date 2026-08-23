"""Redis Streams buffers between ingest and the ClickHouse batchers."""

from redis.asyncio import Redis

from oriflux.models.api_metrics import ApiMinuteRow
from oriflux.models.events import EnrichedEvent

EVENTS_STREAM = "oriflux:events"
CONSUMER_GROUP = "batcher"

API_METRICS_STREAM = "oriflux:api_metrics"
API_CONSUMER_GROUP = "api-batcher"

# Safety caps so a dead batcher can't grow Redis unbounded; ~ makes them
# approximate (cheap). Events: at 500 evt/s this is > 30 min of headroom.
_STREAM_MAXLEN = 1_000_000
# api_minutely rows are ~500 B each and arrive at ~50k/day in prod: 1M rows
# is ~500 MB — enough to OOM a 512 MB Redis (incident 2026-08-23). 250k rows
# (~125 MB) is still > 4 days of backlog for a stalled batcher.
_API_STREAM_MAXLEN = 250_000


async def publish_event(redis: Redis, event: EnrichedEvent) -> None:
    await redis.xadd(
        EVENTS_STREAM,
        {"payload": event.model_dump_json()},
        maxlen=_STREAM_MAXLEN,
        approximate=True,
    )


async def publish_api_rows(redis: Redis, rows: list[ApiMinuteRow]) -> None:
    async with redis.pipeline(transaction=False) as pipe:
        for row in rows:
            pipe.xadd(
                API_METRICS_STREAM,
                {"payload": row.model_dump_json()},
                maxlen=_API_STREAM_MAXLEN,
                approximate=True,
            )
        await pipe.execute()
