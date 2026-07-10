"""Seam: the batcher — Redis Streams consumer group → ClickHouse sink.

At-least-once contract (PRD §8.3): XACK happens ONLY after the sink insert
commits. A batcher that dies between insert and ack must re-deliver the same
events (same UUIDs) on restart; deduplication then happens in ClickHouse on
the event UUID (integration-tested). Uses fakeredis for real stream
semantics and a fake sink at the storage boundary.
"""

from datetime import UTC, datetime

import pytest
from fakeredis import FakeAsyncRedis

from oriflux.models.events import EnrichedEvent, PageviewIn
from oriflux.storage.redis_stream import EVENTS_STREAM, publish_event
from oriflux.workers.batcher import Batcher


def make_event() -> EnrichedEvent:
    wire = PageviewIn.model_validate({"type": "pageview", "url": "https://a.io/"})
    return EnrichedEvent.from_pageview(
        wire, org_id="org-dev", project_id="proj-dev",
        timestamp=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    )


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[list[EnrichedEvent]] = []

    def insert(self, events: list[EnrichedEvent]) -> None:
        self.batches.append(events)


class FailingSink:
    def insert(self, events: list[EnrichedEvent]) -> None:
        raise ConnectionError("clickhouse is down")


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()


async def pending_count(redis: FakeAsyncRedis) -> int:
    info = await redis.xpending(EVENTS_STREAM, "batcher")
    return int(info["pending"])


class TestAckAfterInsert:
    async def test_consumed_events_are_inserted_then_acked(self, redis: FakeAsyncRedis) -> None:
        event = make_event()
        await publish_event(redis, event)
        sink = RecordingSink()
        batcher = Batcher(redis, sink, consumer="c1")

        processed = await batcher.run_once()

        assert processed == 1
        assert [e.event_id for e in sink.batches[0]] == [event.event_id]
        assert await pending_count(redis) == 0

    async def test_failed_insert_leaves_events_pending_and_unacked(
        self, redis: FakeAsyncRedis
    ) -> None:
        await publish_event(redis, make_event())
        batcher = Batcher(redis, FailingSink(), consumer="c1")

        with pytest.raises(ConnectionError):
            await batcher.run_once()

        assert await pending_count(redis) == 1

    async def test_restart_after_crash_redelivers_the_same_event_uuid(
        self, redis: FakeAsyncRedis
    ) -> None:
        event = make_event()
        await publish_event(redis, event)
        crashing = Batcher(redis, FailingSink(), consumer="c1")
        with pytest.raises(ConnectionError):
            await crashing.run_once()

        # same consumer name restarts with a working sink
        sink = RecordingSink()
        recovered = Batcher(redis, sink, consumer="c1")
        processed = await recovered.run_once()

        assert processed == 1
        assert [e.event_id for e in sink.batches[0]] == [event.event_id]
        assert await pending_count(redis) == 0

    async def test_run_once_with_empty_stream_processes_nothing(
        self, redis: FakeAsyncRedis
    ) -> None:
        batcher = Batcher(redis, RecordingSink(), consumer="c1")
        assert await batcher.run_once() == 0
