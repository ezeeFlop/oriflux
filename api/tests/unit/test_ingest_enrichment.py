"""Seam: the ingest HTTP surface with enrichment wired in (issue #4).

DNT/GPC honored, geo/UA/traffic-class/visitor-hash stamped on the event,
UTM extraction, and the privacy invariant: the caller's IP appears nowhere
in the buffered event.
"""

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings
from oriflux.ingest.main import create_app
from oriflux.models.events import EnrichedEvent
from oriflux.storage.redis_stream import EVENTS_STREAM
from tests.unit.test_ingest_auth import Seeded, auth, seed

FIXTURES = str(Path(__file__).parent.parent / "fixtures" / "geoip")
LONDON_IP = "81.2.69.142"  # MaxMind test-database canonical London IP
CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
GPTBOT = "GPTBot/1.2 (+https://openai.com/gptbot)"


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


async def collect(
    client: httpx.AsyncClient,
    seeded: Seeded,
    *,
    url: str = "https://audigeo.ai/pricing",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        "/api/v1/events",
        json={"type": "pageview", "url": url},
        headers={**auth(seeded.ingest_key), **(headers or {})},
    )


async def buffered_event(redis: FakeAsyncRedis) -> EnrichedEvent:
    entries = await redis.xrange(EVENTS_STREAM)
    assert len(entries) == 1
    return EnrichedEvent.model_validate_json(entries[0][1][b"payload"])


class TestDntGpc:
    async def test_dnt_requests_are_not_tracked(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await collect(client, seeded, headers={"DNT": "1"})
        assert response.status_code == 202
        assert response.json() == {"tracked": False}
        assert await redis.xlen(EVENTS_STREAM) == 0

    async def test_gpc_requests_are_not_tracked(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await collect(client, seeded, headers={"Sec-GPC": "1"})
        assert response.status_code == 202
        assert await redis.xlen(EVENTS_STREAM) == 0


class TestEnrichedDimensions:
    async def test_geo_ua_and_visitor_hash_are_stamped(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await collect(
            client,
            seeded,
            headers={
                "X-Forwarded-For": LONDON_IP,
                "User-Agent": CHROME_MAC,
                "Accept-Language": "fr-FR,fr;q=0.9",
            },
        )
        assert response.status_code == 202
        event = await buffered_event(redis)
        assert event.country == "GB"
        assert event.region == "England"
        assert event.city == "London"
        assert event.browser == "Chrome"
        assert event.os == "Mac OS X"
        assert event.traffic_class == "human"
        assert event.locale == "fr-FR"
        assert len(event.visitor_hash) == 64

    async def test_gptbot_event_is_classified_ai_agent(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        await collect(client, seeded, headers={"User-Agent": GPTBOT})
        assert (await buffered_event(redis)).traffic_class == "ai_agent"

    async def test_utm_params_are_extracted(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        await collect(
            client,
            seeded,
            url="https://audigeo.ai/?utm_source=newsletter&utm_medium=email&utm_campaign=q3",
        )
        event = await buffered_event(redis)
        assert event.utm_source == "newsletter"
        assert event.utm_medium == "email"
        assert event.utm_campaign == "q3"

    async def test_same_visitor_hashes_identically_across_two_events(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        headers = {"X-Forwarded-For": LONDON_IP, "User-Agent": CHROME_MAC}
        await collect(client, seeded, headers=headers)
        await collect(client, seeded, headers=headers)
        entries = await redis.xrange(EVENTS_STREAM)
        events = [EnrichedEvent.model_validate_json(e[1][b"payload"]) for e in entries]
        assert events[0].visitor_hash == events[1].visitor_hash


class TestIpIsDiscarded:
    async def test_the_raw_ip_appears_nowhere_in_the_buffered_event(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        """PRD §9: IP resolved at ingestion then destroyed, never persisted."""
        await collect(
            client, seeded, headers={"X-Forwarded-For": LONDON_IP, "User-Agent": CHROME_MAC}
        )
        entries = await redis.xrange(EVENTS_STREAM)
        raw_payload = entries[0][1][b"payload"].decode()
        assert LONDON_IP not in raw_payload

    async def test_the_raw_ip_appears_nowhere_in_application_logs(
        self,
        client: httpx.AsyncClient,
        seeded: Seeded,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Issue #4: '…nowhere in ClickHouse or logs'. Application loggers must
        never emit the IP (uvicorn access logs are disabled in deploy files)."""
        with caplog.at_level(logging.DEBUG):
            await collect(
                client, seeded, headers={"X-Forwarded-For": LONDON_IP, "User-Agent": CHROME_MAC}
            )
        assert LONDON_IP not in caplog.text

    async def test_the_rate_limit_buckets_do_not_contain_the_raw_ip(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        await collect(
            client, seeded, headers={"X-Forwarded-For": LONDON_IP, "User-Agent": CHROME_MAC}
        )
        keys = [k.decode() for k in await redis.keys("oriflux:rl:*")]
        assert keys, "rate limiting must have recorded the request"
        assert all(LONDON_IP not in k for k in keys)
