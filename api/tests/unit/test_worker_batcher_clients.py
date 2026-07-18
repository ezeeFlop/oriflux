"""Seam: each Redis→ClickHouse batcher gets its OWN ClickHouse client.

Root cause of the prod "Attempt to execute concurrent queries within the same
session" errors (188/24h, events left pending): the events batcher and the
api-minutely batcher run as concurrent asyncio tasks but shared ONE
clickhouse_connect client — one session. clickhouse_connect clients are not
thread-safe, so two overlapping `insert`s on one session are rejected by
ClickHouse. Each batcher must own a separate client.
"""

from fakeredis import FakeAsyncRedis

from oriflux.workers import main as worker_main


class FakeCHClient:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


async def test_each_batcher_owns_a_separate_clickhouse_client(monkeypatch):
    made: list[FakeCHClient] = []

    def fake_wait(settings, **kwargs):
        client = FakeCHClient()
        made.append(client)
        return client

    monkeypatch.setattr(worker_main, "wait_for_clickhouse", fake_wait)
    monkeypatch.setattr(worker_main, "ensure_schema", lambda client: None)

    captured_sinks: list[object] = []
    real_batcher = worker_main.Batcher

    class SpyBatcher(real_batcher):  # type: ignore[valid-type,misc]
        def __init__(self, redis, sink, **kwargs):
            captured_sinks.append(sink)
            super().__init__(redis, sink, **kwargs)

        async def run_forever(self) -> None:
            return  # don't spin the infinite consumer loop under test

    monkeypatch.setattr(worker_main, "Batcher", SpyBatcher)
    monkeypatch.setattr(worker_main.Redis, "from_url", lambda url: FakeAsyncRedis())

    app = worker_main.create_app()
    async with app.router.lifespan_context(app):
        pass

    assert len(captured_sinks) == 2
    # the two concurrent batchers must not share one (non-thread-safe) client
    assert captured_sinks[0]._client is not captured_sinks[1]._client
