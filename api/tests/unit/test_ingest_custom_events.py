"""Seam: custom events + identify on the ingest HTTP surface (issue #17).

track() events land as EnrichedEvent rows; identify() binds the current
session server-side so subsequent events carry user_pseudo_id — with zero
client-side storage. PII in identify dies here with a 422 naming the reason.
"""

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
CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


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


async def post_event(
    client: httpx.AsyncClient, seeded: Seeded, payload: dict[str, object]
) -> httpx.Response:
    return await client.post(
        "/api/v1/events",
        json=payload,
        headers={**auth(seeded.ingest_key), "User-Agent": CHROME},
    )


async def buffered_events(redis: FakeAsyncRedis) -> list[EnrichedEvent]:
    entries = await redis.xrange(EVENTS_STREAM)
    return [EnrichedEvent.model_validate_json(e[1][b"payload"]) for e in entries]


class TestCustomEvents:
    async def test_track_lands_as_an_enriched_event(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await post_event(
            client,
            seeded,
            {"type": "event", "name": "signup_completed",
             "url": "https://audigeo.ai/join", "props": {"plan": "pro"}},
        )
        assert response.status_code == 202
        [event] = await buffered_events(redis)
        assert event.event_name == "signup_completed"
        assert event.source_type == "web"
        assert event.url_path == "/join"
        assert event.props == {"plan": "pro"}
        assert event.visitor_hash != ""
        assert event.session_id != ""

    async def test_track_with_inline_user_id_stamps_user_pseudo_id(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        await post_event(
            client, seeded, {"type": "event", "name": "upgrade", "user_id": "usr_42"}
        )
        [event] = await buffered_events(redis)
        assert event.user_pseudo_id == "usr_42"


class TestIdentify:
    async def test_identify_binds_the_session_for_subsequent_events(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await post_event(
            client, seeded, {"type": "identify", "user_id": "usr_42"}
        )
        assert response.status_code == 202
        assert response.json() == {"identified": True}
        assert await redis.xlen(EVENTS_STREAM) == 0  # identify emits no event row

        await post_event(
            client, seeded, {"type": "pageview", "url": "https://audigeo.ai/app"}
        )
        [pageview] = await buffered_events(redis)
        assert pageview.user_pseudo_id == "usr_42"

    async def test_pii_identify_is_rejected_naming_the_reason(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await post_event(
            client, seeded, {"type": "identify", "user_id": "jane@corp.io"}
        )
        assert response.status_code == 422
        assert "email" in response.text
        assert await redis.xlen(EVENTS_STREAM) == 0

    async def test_dnt_skips_identify(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await client.post(
            "/api/v1/events",
            json={"type": "identify", "user_id": "usr_42"},
            headers={**auth(seeded.ingest_key), "User-Agent": CHROME, "DNT": "1"},
        )
        assert response.status_code == 202
        assert response.json() == {"tracked": False}
