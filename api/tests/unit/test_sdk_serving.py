"""Seam: oriflux.js delivery by the ingest service (issue #5).

Versioned path, long-lived immutable caching, ≤ 2 KB gzipped, and the
privacy guarantees the PRD stakes the product on: no cookies, no storage
identifiers in the script. CORS must allow cross-origin POSTs with the
per-source Bearer key.
"""

import gzip
from collections.abc import AsyncIterator

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings
from oriflux.ingest.main import create_app


@pytest.fixture
async def client(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        redis=FakeAsyncRedis(), settings=Settings(), session_factory=db_sessionmaker
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as c:
        yield c


class TestScriptServing:
    async def test_served_at_a_versioned_path_with_immutable_cache(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/v1/oriflux.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        cache = response.headers["cache-control"]
        assert "immutable" in cache
        assert "max-age=" in cache

    async def test_script_is_at_most_2kb_gzipped(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/v1/oriflux.js")
        assert len(gzip.compress(response.content, 9)) <= 2048

    async def test_script_uses_no_cookies_and_no_storage_identifiers(
        self, client: httpx.AsyncClient
    ) -> None:
        source = (await client.get("/v1/oriflux.js")).text
        assert "document.cookie" not in source
        assert "localStorage" not in source
        assert "sessionStorage" not in source
        assert "indexedDB" not in source

    async def test_script_defaults_to_the_central_endpoint_and_reads_the_override(
        self, client: httpx.AsyncClient
    ) -> None:
        source = (await client.get("/v1/oriflux.js")).text
        assert "in.oriflux.sponge-theory.dev" in source  # central default (décision 2026-07-10)
        assert "data-endpoint" in source  # per-product override, day one
        assert "data-key" in source


class TestCors:
    async def test_preflight_allows_cross_origin_posts_with_bearer_keys(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.options(
            "/api/v1/events",
            headers={
                "Origin": "https://audigeo.ai",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
        allowed = response.headers["access-control-allow-headers"].lower()
        assert "authorization" in allowed
        assert int(response.headers["access-control-max-age"]) >= 3600


class TestProductAnalyticsApi:
    """§5.2 / issue #17: window.oriflux.track / .identify shipped in the tag."""

    async def test_script_exposes_track_and_identify(self, client: httpx.AsyncClient) -> None:
        source = (await client.get("/v1/oriflux.js")).text
        assert "track:" in source
        assert "identify:" in source
        assert "oriflux" in source  # window.oriflux namespace
