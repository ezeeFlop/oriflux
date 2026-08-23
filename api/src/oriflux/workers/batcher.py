"""Micro-batcher: Redis Streams consumer group → ClickHouse inserts.

At-least-once delivery (PRD §8.3, décision 2026-07-10):
- events are read through a consumer group, so undelivered and un-acked
  entries survive a batcher crash;
- XACK is sent ONLY after the sink insert returned (ClickHouse commit);
- a restart first drains this consumer's pending entries (id "0") before
  reading new ones (">"), so an insert-then-crash re-delivers the same
  event UUIDs and ClickHouse dedups them (ReplacingMergeTree on event_id);
- consumer names are hostnames, so a restarted container is a NEW consumer:
  entries left pending on a dead consumer are claimed (XAUTOCLAIM) once
  that consumer has been idle for `claim_idle_ms`, and idle consumers
  with nothing pending are pruned (prod 2026-08-23: 52 ghost consumers,
  4 entries stuck forever);
- every loop iteration records a tick; a batcher hung inside an insert
  stops ticking and the workers' /healthz turns unhealthy so Swarm
  restarts the task (prod 2026-08-21: 2 days frozen, Redis OOM).
"""

import asyncio
import logging
import time
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
        claim_idle_ms: int = 60_000,
    ) -> None:
        self._redis = redis
        self._sink = sink
        self._consumer = consumer
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._stream = stream
        self._group = group
        self._model = model
        self._claim_idle_ms = claim_idle_ms
        self.last_tick: float | None = None

    def is_alive(self, *, max_idle_s: float) -> bool:
        """False once the loop has stopped ticking for `max_idle_s` (hung insert)."""
        if self.last_tick is None:
            return True  # not started yet — startup is covered by the task itself
        return (time.monotonic() - self.last_tick) <= max_idle_s

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

    async def _claim_orphans(self) -> list[tuple[bytes, dict[bytes, bytes]]]:
        """Take over entries pending on consumers idle for > claim_idle_ms and
        prune idle consumers that have nothing pending (hostname consumer
        names accumulate one ghost per restart)."""
        response: Any = await self._redis.xautoclaim(
            self._stream,
            self._group,
            self._consumer,
            min_idle_time=self._claim_idle_ms,
            start_id="0-0",
            count=self._batch_size,
        )
        # Redis 7 returns [next_id, entries, deleted_ids]; 6.2 returns two items.
        entries: list[tuple[bytes, dict[bytes, bytes]]] = list(response[1]) if response else []
        if entries:
            logger.warning("claimed %d entries orphaned by dead consumers", len(entries))
        consumers: Any = await self._redis.xinfo_consumers(self._stream, self._group)
        for consumer in consumers:
            name = consumer["name"]
            name_str = name.decode() if isinstance(name, bytes) else str(name)
            if (
                name_str != self._consumer
                and int(consumer["pending"]) == 0
                and int(consumer["idle"]) >= self._claim_idle_ms
            ):
                await self._redis.xgroup_delconsumer(self._stream, self._group, name_str)
        return entries

    async def run_once(self, *, block_ms: int | None = None) -> int:
        """Process one micro-batch. Returns the number of events acked."""
        await self._ensure_group()
        # Crash recovery first: entries delivered to this consumer but never acked.
        entries = await self._read_batch("0", None)
        if not entries:
            entries = await self._claim_orphans()
        if not entries:
            entries = await self._read_batch(">", block_ms)
        self.last_tick = time.monotonic()
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
        self.last_tick = time.monotonic()
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
