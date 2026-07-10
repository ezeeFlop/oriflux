"""Seam: /api/v1/query auth + org scoping (issue #3 acceptance).

Every registry query is scoped by the org of the read key that made it —
a user of org A can never read org B data. The SQL-parameter proof lives
here (fake executor); the end-to-end proof against real ClickHouse lives
in tests/integration.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.api.main import create_app
from oriflux.db.models import ApiKey, KeyScope, Organization
from oriflux.security.keys import generate_api_key
from tests.unit.conftest import TEST_SETTINGS, FakeExecutor, FakeGoogle

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}
VALID = {"metric": "pageviews", "period": JULY}


async def seed_two_orgs(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, str], dict[str, str]]:
    """Two orgs, each with a read key and an ingest key; returns per-org dicts."""
    orgs = []
    async with factory() as session:
        for slug in ("org-a", "org-b"):
            org = Organization(slug=slug, name=slug)
            session.add(org)
            await session.flush()
            read = generate_api_key(KeyScope.read)
            ingest = generate_api_key(KeyScope.ingest)
            session.add(
                ApiKey(
                    org_id=org.id, scope=KeyScope.read,
                    key_hash=read.key_hash, key_prefix=read.key_prefix,
                )
            )
            session.add(
                ApiKey(
                    org_id=org.id, scope=KeyScope.ingest,
                    key_hash=ingest.key_hash, key_prefix=ingest.key_prefix,
                )
            )
            orgs.append(
                {"org_id": str(org.id), "read_key": read.plaintext, "ingest_key": ingest.plaintext}
            )
        await session.commit()
    return orgs[0], orgs[1]


@pytest.fixture
async def client(
    db_sessionmaker: async_sessionmaker[AsyncSession], fake_executor: FakeExecutor
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        executor=fake_executor,
        settings=TEST_SETTINGS,
        session_factory=db_sessionmaker,
        google_verifier=FakeGoogle(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as c:
        yield c


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class TestQueryAuth:
    async def test_missing_key_is_401(self, client: httpx.AsyncClient) -> None:
        assert (await client.post("/api/v1/query", json=VALID)).status_code == 401

    async def test_unknown_key_is_401(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/query", json=VALID, headers=auth("ofx_read_forged"))
        assert response.status_code == 401

    async def test_ingest_scoped_key_cannot_query(
        self, client: httpx.AsyncClient, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        org_a, _ = await seed_two_orgs(db_sessionmaker)
        response = await client.post(
            "/api/v1/query", json=VALID, headers=auth(org_a["ingest_key"])
        )
        assert response.status_code == 403


class TestOrgScoping:
    async def test_every_query_is_scoped_to_the_keys_org(
        self,
        client: httpx.AsyncClient,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        fake_executor: FakeExecutor,
    ) -> None:
        org_a, org_b = await seed_two_orgs(db_sessionmaker)

        for org in (org_a, org_b):
            response = await client.post(
                "/api/v1/query", json=VALID, headers=auth(org["read_key"])
            )
            assert response.status_code == 200
            _, params = fake_executor.calls[-1]
            assert params["org_id"] == org["org_id"]

        # org A's key never produced a query bound to org B's id
        a_calls = [p for _, p in fake_executor.calls if p["org_id"] == org_a["org_id"]]
        b_calls = [p for _, p in fake_executor.calls if p["org_id"] == org_b["org_id"]]
        assert len(a_calls) == 1 and len(b_calls) == 1
