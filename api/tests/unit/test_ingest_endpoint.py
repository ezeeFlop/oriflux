"""Seam: the ingest HTTP surface — POST /api/v1/events.

Auth (hardcoded dev key for the skeleton), Pydantic validation, UUID
assignment, publish to the Redis stream, 202. Redis is faked at the
storage boundary; everything above it is the real app.
"""

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from oriflux.ingest.main import create_app
from oriflux.models.events import EnrichedEvent
from oriflux.storage.redis_stream import EVENTS_STREAM

VALID = {"type": "pageview", "url": "https://sponge-theory.ai/", "referrer": ""}


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()


@pytest.fixture
async def client(redis: FakeAsyncRedis) -> httpx.AsyncClient:
    app = create_app(redis=redis)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://ingest")


def auth(key: str = "dev-ingest-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class TestCollectEndpoint:
    async def test_valid_pageview_is_accepted_and_buffered(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis
    ) -> None:
        response = await client.post("/api/v1/events", json=VALID, headers=auth())

        assert response.status_code == 202
        assert "event_id" in response.json()
        entries = await redis.xrange(EVENTS_STREAM)
        assert len(entries) == 1
        event = EnrichedEvent.model_validate_json(entries[0][1][b"payload"])
        assert str(event.event_id) == response.json()["event_id"]
        assert event.org_id == "org-dev"
        assert event.project_id == "proj-dev"

    async def test_missing_key_is_401(self, client: httpx.AsyncClient) -> None:
        assert (await client.post("/api/v1/events", json=VALID)).status_code == 401

    async def test_wrong_key_is_401(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/events", json=VALID, headers=auth("nope"))
        assert response.status_code == 401

    async def test_invalid_payload_is_422_and_not_buffered(
        self, client: httpx.AsyncClient, redis: FakeAsyncRedis
    ) -> None:
        response = await client.post("/api/v1/events", json={"type": "pageview"}, headers=auth())
        assert response.status_code == 422
        assert await redis.xlen(EVENTS_STREAM) == 0

    async def test_healthz(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/healthz")
        assert response.status_code == 200
