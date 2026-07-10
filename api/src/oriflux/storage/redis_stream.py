"""Redis Streams buffer between ingest and the ClickHouse batcher."""

from redis.asyncio import Redis

from oriflux.models.events import EnrichedEvent

EVENTS_STREAM = "oriflux:events"
CONSUMER_GROUP = "batcher"

# Safety cap so a dead batcher can't grow Redis unbounded; ~ makes it
# approximate (cheap). At 500 evt/s this is > 30 min of headroom.
_STREAM_MAXLEN = 1_000_000


async def publish_event(redis: Redis, event: EnrichedEvent) -> None:
    await redis.xadd(
        EVENTS_STREAM,
        {"payload": event.model_dump_json()},
        maxlen=_STREAM_MAXLEN,
        approximate=True,
    )
