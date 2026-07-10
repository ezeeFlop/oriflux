"""Integration fixtures — require the deploy/ docker compose stack.

Endpoints are env-overridable so the same tests can run in CI later.
Unavailable services skip (not fail) so `uv run pytest` stays green without
docker; run explicitly with `uv run pytest -m integration`.
"""

import os

import httpx
import pytest
from redis.asyncio import Redis

from oriflux.config import Settings

INGEST_URL = os.environ.get("ORIFLUX_TEST_INGEST_URL", "http://localhost:8100")
API_URL = os.environ.get("ORIFLUX_TEST_API_URL", "http://localhost:8101")
WORKERS_URL = os.environ.get("ORIFLUX_TEST_WORKERS_URL", "http://localhost:8102")
REDIS_URL = os.environ.get("ORIFLUX_TEST_REDIS_URL", "redis://localhost:6380/0")


def _stack_settings() -> Settings:
    return Settings(redis_url=REDIS_URL)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return _stack_settings()


@pytest.fixture(scope="session", autouse=True)
def require_stack() -> None:
    try:
        httpx.get(f"{INGEST_URL}/healthz", timeout=2.0).raise_for_status()
        httpx.get(f"{API_URL}/healthz", timeout=2.0).raise_for_status()
    except Exception:
        pytest.skip("deploy/ docker compose stack is not running")


@pytest.fixture
async def redis(settings: Settings) -> Redis:
    client = Redis.from_url(settings.redis_url)
    yield client
    await client.aclose()
