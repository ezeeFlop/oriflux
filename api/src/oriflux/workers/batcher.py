"""Micro-batcher: Redis Streams consumer group → ClickHouse inserts.

At-least-once delivery (PRD §8.3, décision 2026-07-10):
- events are read through a consumer group, so undelivered and un-acked
  entries survive a batcher crash;
- XACK is sent ONLY after the sink insert returned (ClickHouse commit);
- a restart first drains this consumer's pending entries (id "0") before
  reading new ones (">"), so an insert-then-crash re-delivers the same
  event UUIDs and ClickHouse dedups them (ReplacingMergeTree on event_id).
"""

import asyncio
import logging
from typing import Any, Protocol

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from oriflux.models.events import EnrichedEvent
from oriflux.storage.redis_stream import CONSUMER_GROUP, EVENTS_STREAM

logger = logging.getLogger(__name__)


class EventSink(Protocol):
    def insert(self, events: list[Any]) -> None: ...


class Batcher:
    def __init__(
        self,
        redis: Redis,
        sink: EventSink,
        *,
        consumer: str,
        batch_size: int = 500,
        block_ms: int = 1000,
        stream: str = EVENTS_STREAM,
        group: str = CONSUMER_GROUP,
        model: type[BaseModel] = EnrichedEvent,
    ) -> None:
        self._redis = redis
        self._sink = sink
        self._consumer = consumer
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._stream = stream
        self._group = group
        self._model = model

    async def _ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _read_batch(
        self, from_id: str, block_ms: int | None
    ) -> list[tuple[bytes, dict[bytes, bytes]]]:
        # redis-py's stubs type xreadgroup too loosely to be useful; the shape
        # is [[stream, [(entry_id, {field: value}), ...]], ...].
        response: Any = await self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: from_id},
            count=self._batch_size,
            block=block_ms,
        )
        if not response:
            return []
        entries: list[tuple[bytes, dict[bytes, bytes]]] = response[0][1]
        return entries

    async def run_once(self, *, block_ms: int | None = None) -> int:
        """Process one micro-batch. Returns the number of events acked."""
        await self._ensure_group()
        # Crash recovery first: entries delivered to this consumer but never acked.
        entries = await self._read_batch("0", None)
        if not entries:
            entries = await self._read_batch(">", block_ms)
        if not entries:
            return 0

        ids: list[bytes] = []
        events: list[BaseModel] = []
        for entry_id, fields in entries:
            payload = fields.get(b"payload") or fields.get("payload")  # type: ignore[call-overload]
            if payload is None:
                logger.error("stream entry %r has no payload field; acking and skipping", entry_id)
                ids.append(entry_id)
                continue
            ids.append(entry_id)
            events.append(self._model.model_validate_json(payload))

        # The insert must commit before anything is acked (at-least-once).
        await asyncio.to_thread(self._sink.insert, events)
        await self._redis.xack(self._stream, self._group, *ids)
        return len(events)

    async def run_forever(self) -> None:
        while True:
            try:
                processed = await self.run_once(block_ms=self._block_ms)
            except Exception:
                logger.exception("batch failed; events stay pending and will be re-delivered")
                await asyncio.sleep(1.0)
                continue
            if processed:
                logger.info("inserted %d events", processed)
