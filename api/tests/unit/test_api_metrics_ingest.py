"""Seam: POST /api/v1/api-metrics — the SDK's aggregate payload (issue #8).

Ingest resolves each entry's caller IP to country/ASN and DISCARDS it: the
rows buffered for ClickHouse must carry geo dimensions but no address.
Overflow entries land as country='unresolved'.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings
from oriflux.ingest.main import create_app
from oriflux.models.api_metrics import ApiMinuteRow
from oriflux.storage.redis_stream import API_METRICS_STREAM
from tests.unit.test_ingest_auth import Seeded, auth, seed

FIXTURES = str(Path(__file__).parent.parent / "fixtures" / "geoip")
LONDON_IP = "81.2.69.142"

PAYLOAD = {
    "window_start": datetime(2026, 7, 10, 14, 3, 27, tzinfo=UTC).isoformat(),
    "overflow_count": 2,
    "entries": [
        {
            "endpoint": "/items/{item_id}", "method": "GET", "status_code": 200,
            "consumer": "acme", "ip": LONDON_IP, "count": 42,
            "bytes_in": 1000, "bytes_out": 9000,
            "latency_ms": {"13": 30, "50": 12}, "overflow": False,
        },
        {
            "endpoint": "/items/{item_id}", "method": "GET", "status_code": 500,
            "consumer": "", "ip": "", "count": 2,
            "latency_ms": {"800": 2}, "overflow": True,
        },
    ],
}


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()


@pytest.fixture
async def seeded(db_sessionmaker: async_sessionmaker[AsyncSession]) -> Seeded:
    return await seed(db_sessionmaker)


@pytest.fixture
async def client(
    redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_key_cache_ttl_s=0.0, geoip_dir=FIXTURES)
    app = create_app(redis=redis, settings=settings, session_factory=db_sessionmaker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as c:
        yield c


async def buffered_rows(redis: FakeAsyncRedis) -> list[ApiMinuteRow]:
    entries = await redis.xrange(API_METRICS_STREAM)
    return [ApiMinuteRow.model_validate_json(e[1][b"payload"]) for e in entries]


class TestApiMetricsIngest:
    async def test_entries_are_geo_resolved_and_buffered(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await client.post(
            "/api/v1/api-metrics", json=PAYLOAD, headers=auth(seeded.ingest_key)
        )
        assert response.status_code == 202, response.text
        rows = await buffered_rows(redis)
        assert len(rows) == 2
        ok = next(r for r in rows if r.status_code == 200)
        assert ok.country == "GB"
        assert ok.org_id == str(seeded.org_id)
        assert ok.status_class == "2xx"
        assert ok.consumer_id == "acme"
        assert ok.latency_bucket_ms == [13.0, 50.0]
        assert ok.latency_counts == [30, 12]
        assert ok.timestamp_min.second == 0  # floored to the minute

    async def test_the_caller_ip_is_discarded(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        await client.post("/api/v1/api-metrics", json=PAYLOAD, headers=auth(seeded.ingest_key))
        raw = b" ".join(e[1][b"payload"] for e in await redis.xrange(API_METRICS_STREAM))
        assert LONDON_IP.encode() not in raw

    async def test_overflow_entries_are_marked_unresolved(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        await client.post("/api/v1/api-metrics", json=PAYLOAD, headers=auth(seeded.ingest_key))
        overflow = next(r for r in await buffered_rows(redis) if r.status_code == 500)
        assert overflow.country == "unresolved"

    async def test_auth_is_enforced_like_events(
        self, client: httpx.AsyncClient, seeded: Seeded
    ) -> None:
        assert (await client.post("/api/v1/api-metrics", json=PAYLOAD)).status_code == 401
        read_scoped = await client.post(
            "/api/v1/api-metrics", json=PAYLOAD, headers=auth(seeded.read_key)
        )
        assert read_scoped.status_code == 403

    async def test_garbage_entries_are_rejected(
        self, client: httpx.AsyncClient, seeded: Seeded
    ) -> None:
        bad = {**PAYLOAD, "entries": [{**PAYLOAD["entries"][0], "status_code": 999}]}
        response = await client.post(
            "/api/v1/api-metrics", json=bad, headers=auth(seeded.ingest_key)
        )
        assert response.status_code == 422
