"""Seam: the query HTTP surface — POST /api/v1/query mechanics.

Auth/scoping proofs live in test_query_org_scoping.py; this file pins the
query behavior itself (rows, schema rejection, compare_to). ClickHouse is
faked at the executor boundary; SQL correctness against a real ClickHouse
is integration-tested.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.api.main import create_app
from oriflux.db.models import ApiKey, KeyScope, Organization
from oriflux.security.keys import generate_api_key
from tests.unit.conftest import TEST_SETTINGS, FakeExecutor, FakeGoogle

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}
VALID = {"metric": "pageviews", "period": JULY}


@pytest.fixture
async def read_key(db_sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    async with db_sessionmaker() as session:
        org = Organization(slug="spt", name="Sponge Theory")
        session.add(org)
        await session.flush()
        issued = generate_api_key(KeyScope.read)
        session.add(
            ApiKey(
                org_id=org.id, scope=KeyScope.read,
                key_hash=issued.key_hash, key_prefix=issued.key_prefix,
            )
        )
        await session.commit()
    return issued.plaintext


@pytest.fixture
def executor() -> FakeExecutor:
    executor = FakeExecutor()
    executor.rows = [{"value": 42}]
    return executor


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


class TestQueryEndpoint:
    async def test_valid_query_returns_rows(
        self, client: httpx.AsyncClient, executor: FakeExecutor, read_key: str
    ) -> None:
        response = await client.post(
            "/api/v1/query", json=VALID, headers={"Authorization": f"Bearer {read_key}"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["metric"] == "pageviews"
        assert body["results"] == [{"value": 42}]
        assert len(executor.calls) == 1

    async def test_unknown_metric_is_422(self, client: httpx.AsyncClient, read_key: str) -> None:
        response = await client.post(
            "/api/v1/query",
            json={"metric": "profit_margin", "period": JULY},
            headers={"Authorization": f"Bearer {read_key}"},
        )
        assert response.status_code == 422

    async def test_unknown_dimension_is_422(
        self, client: httpx.AsyncClient, read_key: str
    ) -> None:
        response = await client.post(
            "/api/v1/query",
            json={**VALID, "dimensions": ["favorite_color"]},
            headers={"Authorization": f"Bearer {read_key}"},
        )
        assert response.status_code == 422

    async def test_compare_to_previous_period_runs_a_shifted_query(
        self, client: httpx.AsyncClient, executor: FakeExecutor, read_key: str
    ) -> None:
        response = await client.post(
            "/api/v1/query",
            json={**VALID, "compare_to": "previous_period"},
            headers={"Authorization": f"Bearer {read_key}"},
        )
        assert response.status_code == 200
        assert response.json()["compare_results"] == [{"value": 42}]
        assert len(executor.calls) == 2
        # previous period = same duration (31 days) immediately before the window
        _, compare_params = executor.calls[1]
        assert compare_params["start"] == datetime(2026, 5, 31, tzinfo=UTC)
        assert compare_params["end"] == datetime(2026, 7, 1, tzinfo=UTC)

    async def test_healthz(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/healthz")).status_code == 200
