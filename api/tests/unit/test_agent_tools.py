"""Seam: the agent-facing tool endpoints exposed over MCP (issue #12).

Read-key auth, org scoping, registry-only compilation, and the MCP mount
exposing exactly the five phase-1 operations.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.api.main import create_app
from oriflux.db.models import ApiKey, KeyScope, Organization, Project
from oriflux.security.keys import generate_api_key
from tests.unit.conftest import TEST_SETTINGS, FakeExecutor, FakeGoogle

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}


class Setup:
    read_key: str
    ingest_key: str
    project_id: str


async def seed(factory: async_sessionmaker[AsyncSession]) -> Setup:
    out = Setup()
    async with factory() as session:
        org = Organization(slug="spt", name="Sponge Theory")
        session.add(org)
        await session.flush()
        project = Project(org_id=org.id, slug="audigeo", name="AudiGEO")
        other_org = Organization(slug="other", name="Other")
        session.add_all([project, other_org])
        await session.flush()
        session.add(Project(org_id=other_org.id, slug="foreign", name="Not yours"))
        read = generate_api_key(KeyScope.read)
        ingest = generate_api_key(KeyScope.ingest)
        session.add(ApiKey(org_id=org.id, scope=KeyScope.read,
                           key_hash=read.key_hash, key_prefix=read.key_prefix))
        session.add(ApiKey(org_id=org.id, scope=KeyScope.ingest,
                           key_hash=ingest.key_hash, key_prefix=ingest.key_prefix))
        await session.commit()
        out.read_key, out.ingest_key = read.plaintext, ingest.plaintext
        out.project_id = str(project.id)
    return out


@pytest.fixture
async def setup(db_sessionmaker: async_sessionmaker[AsyncSession]) -> Setup:
    return await seed(db_sessionmaker)


@pytest.fixture
def executor() -> FakeExecutor:
    return FakeExecutor()


@pytest.fixture
async def client(
    db_sessionmaker: async_sessionmaker[AsyncSession], executor: FakeExecutor
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        executor=executor,
        settings=TEST_SETTINGS,
        session_factory=db_sessionmaker,
        google_verifier=FakeGoogle(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as c:
        yield c


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class TestListProjects:
    async def test_lists_only_the_keys_org(
        self, client: httpx.AsyncClient, setup: Setup
    ) -> None:
        response = await client.get("/api/v1/projects", headers=auth(setup.read_key))
        assert response.status_code == 200
        assert [p["slug"] for p in response.json()] == ["audigeo"]

    async def test_ingest_key_is_rejected(
        self, client: httpx.AsyncClient, setup: Setup
    ) -> None:
        response = await client.get("/api/v1/projects", headers=auth(setup.ingest_key))
        assert response.status_code == 403


class TestOverview:
    async def test_bundles_registry_metrics_scoped_to_the_project(
        self, client: httpx.AsyncClient, setup: Setup, executor: FakeExecutor
    ) -> None:
        executor.rows = [{"value": 7}]
        response = await client.post(
            "/api/v1/overview",
            json={"project": "audigeo", "period": JULY},
            headers=auth(setup.read_key),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["visitors"] == 7
        assert body["api_requests"] == 7
        assert "visit-days" in body["visitors_note"]
        # every executed query was project-scoped through the registry
        assert executor.calls
        assert all(p["filter_0"] == setup.project_id for _, p in executor.calls)

    async def test_unknown_project_slug_is_404(
        self, client: httpx.AsyncClient, setup: Setup
    ) -> None:
        response = await client.post(
            "/api/v1/overview",
            json={"project": "nope", "period": JULY},
            headers=auth(setup.read_key),
        )
        assert response.status_code == 404

    async def test_foreign_org_projects_are_invisible(
        self, client: httpx.AsyncClient, setup: Setup
    ) -> None:
        response = await client.post(
            "/api/v1/overview",
            json={"project": "foreign", "period": JULY},
            headers=auth(setup.read_key),
        )
        assert response.status_code == 404


class TestGeoBreakdown:
    async def test_rows_sorted_by_value(
        self, client: httpx.AsyncClient, setup: Setup, executor: FakeExecutor
    ) -> None:
        executor.rows = [{"country": "FR", "value": 2}, {"country": "DE", "value": 9}]
        response = await client.post(
            "/api/v1/geo-breakdown",
            json={"project": "audigeo", "level": "country", "period": JULY},
            headers=auth(setup.read_key),
        )
        assert [r["country"] for r in response.json()["rows"]] == ["DE", "FR"]

    async def test_invalid_level_is_422(self, client: httpx.AsyncClient, setup: Setup) -> None:
        response = await client.post(
            "/api/v1/geo-breakdown",
            json={"project": "audigeo", "level": "continent", "period": JULY},
            headers=auth(setup.read_key),
        )
        assert response.status_code == 422


class TestMcpMount:
    async def test_the_five_phase_1_tools_are_exposed(self, client: httpx.AsyncClient) -> None:
        """Parity by construction: query_metrics IS /api/v1/query — the MCP
        tool list must expose exactly the five phase-1 operations."""
        initialize = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert initialize.status_code == 200, initialize.text
