"""Integration fixtures — require the deploy/ docker compose stack.

Each session seeds fresh tenants (unique slugs) straight into the compose
PostgreSQL, then exercises the real HTTP services with the issued keys.
Endpoints are env-overridable so the same tests can run in CI later.
Unavailable services skip (not fail); run explicitly with `-m integration`.
"""

import os
import uuid
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from oriflux.config import Settings
from oriflux.db import create_engine, create_session_factory
from oriflux.db.models import ApiKey, KeyScope, Organization, Project, Source, SourceType
from oriflux.security.keys import generate_api_key

INGEST_URL = os.environ.get("ORIFLUX_TEST_INGEST_URL", "http://localhost:8100")
API_URL = os.environ.get("ORIFLUX_TEST_API_URL", "http://localhost:8101")
WORKERS_URL = os.environ.get("ORIFLUX_TEST_WORKERS_URL", "http://localhost:8102")
REDIS_URL = os.environ.get("ORIFLUX_TEST_REDIS_URL", "redis://localhost:6380/0")


@dataclass
class Tenant:
    org_id: str
    project_id: str
    source_id: str
    ingest_key: str
    read_key: str


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(redis_url=REDIS_URL)


@pytest.fixture(scope="session", autouse=True)
def require_stack() -> None:
    try:
        httpx.get(f"{INGEST_URL}/healthz", timeout=2.0).raise_for_status()
        httpx.get(f"{API_URL}/healthz", timeout=2.0).raise_for_status()
    except Exception:
        pytest.skip("deploy/ docker compose stack is not running")


@pytest_asyncio.fixture
async def redis(settings: Settings) -> Redis:
    client = Redis.from_url(settings.redis_url)
    yield client
    await client.aclose()


async def _seed_tenant(factory: async_sessionmaker, slug: str) -> Tenant:
    async with factory() as session:
        org = Organization(slug=slug, name=slug)
        session.add(org)
        await session.flush()
        project = Project(org_id=org.id, slug="it", name="Integration")
        session.add(project)
        await session.flush()
        source = Source(project_id=project.id, type=SourceType.web, name="it web")
        session.add(source)
        await session.flush()
        ingest = generate_api_key(KeyScope.ingest)
        read = generate_api_key(KeyScope.read)
        session.add(
            ApiKey(
                org_id=org.id, source_id=source.id, scope=KeyScope.ingest,
                key_hash=ingest.key_hash, key_prefix=ingest.key_prefix, name="it",
            )
        )
        session.add(
            ApiKey(
                org_id=org.id, scope=KeyScope.read,
                key_hash=read.key_hash, key_prefix=read.key_prefix, name="it",
            )
        )
        await session.commit()
        return Tenant(
            org_id=str(org.id),
            project_id=str(project.id),
            source_id=str(source.id),
            ingest_key=ingest.plaintext,
            read_key=read.plaintext,
        )


@pytest_asyncio.fixture
async def tenants(settings: Settings) -> tuple[Tenant, Tenant]:
    """Two isolated tenants, freshly seeded into the compose PostgreSQL."""
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    run = uuid.uuid4().hex[:8]
    a = await _seed_tenant(factory, f"it-a-{run}")
    b = await _seed_tenant(factory, f"it-b-{run}")
    await engine.dispose()
    return a, b


@pytest_asyncio.fixture
async def tenant(tenants: tuple[Tenant, Tenant]) -> Tenant:
    return tenants[0]
