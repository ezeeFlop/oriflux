"""Seam: the query HTTP surface — POST /api/v1/query.

The endpoint accepts only the typed query object, compiles it through the
registry, and executes it. ClickHouse is faked at the executor boundary;
SQL correctness against a real ClickHouse is integration-tested.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from oriflux.api.main import create_app

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}
VALID = {"metric": "pageviews", "period": JULY}


class FakeExecutor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.rows = rows if rows is not None else [{"value": 42}]

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((sql, params))
        return self.rows


@pytest.fixture
def executor() -> FakeExecutor:
    return FakeExecutor()


@pytest.fixture
async def client(executor: FakeExecutor) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(executor=executor))
    return httpx.AsyncClient(transport=transport, base_url="http://api")


def auth(key: str = "dev-read-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class TestQueryEndpoint:
    async def test_valid_query_returns_rows(
        self, client: httpx.AsyncClient, executor: FakeExecutor
    ) -> None:
        response = await client.post("/api/v1/query", json=VALID, headers=auth())

        assert response.status_code == 200
        body = response.json()
        assert body["metric"] == "pageviews"
        assert body["results"] == [{"value": 42}]
        assert len(executor.calls) == 1

    async def test_unknown_metric_is_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/query", json={"metric": "revenue", "period": JULY}, headers=auth()
        )
        assert response.status_code == 422

    async def test_unknown_dimension_is_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/query", json={**VALID, "dimensions": ["favorite_color"]}, headers=auth()
        )
        assert response.status_code == 422

    async def test_missing_key_is_401(self, client: httpx.AsyncClient) -> None:
        assert (await client.post("/api/v1/query", json=VALID)).status_code == 401

    async def test_compare_to_previous_period_runs_a_shifted_query(
        self, client: httpx.AsyncClient, executor: FakeExecutor
    ) -> None:
        response = await client.post(
            "/api/v1/query", json={**VALID, "compare_to": "previous_period"}, headers=auth()
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
