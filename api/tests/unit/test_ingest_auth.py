"""Seam: ingest key auth + rate limiting (issue #3 acceptance).

Missing/unknown/revoked keys → 401; a read-scoped key cannot ingest → 403;
a valid per-source ingest key is accepted and the event is stamped with the
source's org/project; per-key and per-IP rate limits answer 429.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings
from oriflux.db.models import ApiKey, KeyScope, Organization, Project, Source, SourceType
from oriflux.ingest.main import create_app
from oriflux.models.events import EnrichedEvent
from oriflux.security.keys import generate_api_key
from oriflux.storage.redis_stream import EVENTS_STREAM

VALID_EVENT = {"type": "pageview", "url": "https://audigeo.ai/"}


class Seeded:
    org_id: uuid.UUID
    project_id: uuid.UUID
    source_id: uuid.UUID
    ingest_key: str
    read_key: str
    revoked_key: str


async def seed(factory: async_sessionmaker[AsyncSession]) -> Seeded:
    out = Seeded()
    async with factory() as session:
        org = Organization(slug="spt", name="Sponge Theory")
        session.add(org)
        await session.flush()
        project = Project(org_id=org.id, slug="audigeo", name="AudiGEO")
        session.add(project)
        await session.flush()
        source = Source(project_id=project.id, type=SourceType.web, name="site")
        session.add(source)
        await session.flush()

        ingest = generate_api_key(KeyScope.ingest)
        read = generate_api_key(KeyScope.read)
        revoked = generate_api_key(KeyScope.ingest)
        session.add(
            ApiKey(
                org_id=org.id, source_id=source.id, scope=KeyScope.ingest,
                key_hash=ingest.key_hash, key_prefix=ingest.key_prefix,
            )
        )
        session.add(
            ApiKey(
                org_id=org.id, scope=KeyScope.read,
                key_hash=read.key_hash, key_prefix=read.key_prefix,
            )
        )
        session.add(
            ApiKey(
                org_id=org.id, source_id=source.id, scope=KeyScope.ingest,
                key_hash=revoked.key_hash, key_prefix=revoked.key_prefix,
                revoked_at=datetime.now(tz=UTC),
            )
        )
        await session.commit()
        out.org_id, out.project_id, out.source_id = org.id, project.id, source.id
        out.ingest_key, out.read_key, out.revoked_key = (
            ingest.plaintext, read.plaintext, revoked.plaintext,
        )
    return out


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()


@pytest.fixture
async def seeded(db_sessionmaker: async_sessionmaker[AsyncSession]) -> Seeded:
    return await seed(db_sessionmaker)


def make_client(
    redis: FakeAsyncRedis,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    **settings_overrides: object,
) -> httpx.AsyncClient:
    settings = Settings(api_key_cache_ttl_s=0.0, **settings_overrides)  # type: ignore[arg-type]
    app = create_app(redis=redis, settings=settings, session_factory=db_sessionmaker)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ingest")


@pytest.fixture
async def client(
    redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(redis, db_sessionmaker) as c:
        yield c


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class TestIngestKeyAuth:
    async def test_valid_key_is_accepted_and_event_stamped_from_source(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await client.post(
            "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.ingest_key)
        )
        assert response.status_code == 202, response.text
        entries = await redis.xrange(EVENTS_STREAM)
        event = EnrichedEvent.model_validate_json(entries[0][1][b"payload"])
        assert event.org_id == str(seeded.org_id)
        assert event.project_id == str(seeded.project_id)

    async def test_missing_key_is_401(self, client: httpx.AsyncClient, seeded: Seeded) -> None:
        assert (await client.post("/api/v1/events", json=VALID_EVENT)).status_code == 401

    async def test_unknown_key_is_401(self, client: httpx.AsyncClient, seeded: Seeded) -> None:
        response = await client.post(
            "/api/v1/events", json=VALID_EVENT, headers=auth("ofx_ing_forged")
        )
        assert response.status_code == 401

    async def test_revoked_key_is_401(self, client: httpx.AsyncClient, seeded: Seeded) -> None:
        response = await client.post(
            "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.revoked_key)
        )
        assert response.status_code == 401

    async def test_read_scoped_key_cannot_ingest(
        self, client: httpx.AsyncClient, seeded: Seeded
    ) -> None:
        response = await client.post(
            "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.read_key)
        )
        assert response.status_code == 403


class TestPayloadAndHealth:
    async def test_invalid_payload_is_422_and_not_buffered(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis, seeded: Seeded
    ) -> None:
        response = await client.post(
            "/api/v1/events", json={"type": "pageview"}, headers=auth(seeded.ingest_key)
        )
        assert response.status_code == 422
        assert await redis.xlen(EVENTS_STREAM) == 0

    async def test_healthz(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/healthz")).status_code == 200


class TestRateLimiting:
    async def test_per_key_limit_answers_429(
        self,
        redis: FakeAsyncRedis,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        seeded: Seeded,
    ) -> None:
        async with make_client(redis, db_sessionmaker, ingest_rate_limit_per_key=3) as client:
            for _ in range(3):
                ok = await client.post(
                    "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.ingest_key)
                )
                assert ok.status_code == 202
            throttled = await client.post(
                "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.ingest_key)
            )
            assert throttled.status_code == 429

    async def test_per_ip_limit_answers_429(
        self,
        redis: FakeAsyncRedis,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        seeded: Seeded,
    ) -> None:
        async with make_client(redis, db_sessionmaker, ingest_rate_limit_per_ip=2) as client:
            for _ in range(2):
                ok = await client.post(
                    "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.ingest_key)
                )
                assert ok.status_code == 202
            throttled = await client.post(
                "/api/v1/events", json=VALID_EVENT, headers=auth(seeded.ingest_key)
            )
            assert throttled.status_code == 429
