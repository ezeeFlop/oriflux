"""Seam: exports (issue #30) — CSV over the same typed query contract."""


import httpx
import pytest

from tests.unit.conftest import FakeExecutor, login
from tests.unit.test_auth_and_admin import create_org_chain

QUERY = {
    "metric": "pageviews",
    "dimensions": ["page"],
    "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"},
}


@pytest.fixture
async def org(api_client: httpx.AsyncClient) -> tuple[dict[str, str], str]:
    owner = await login(api_client, "alice")
    org_id, _, _ = await create_org_chain(api_client, owner)
    return owner, org_id


class TestCsvExport:
    async def test_query_result_streams_as_csv(
        self,
        api_client: httpx.AsyncClient,
        org: tuple[dict[str, str], str],
        fake_executor: FakeExecutor,
    ) -> None:
        owner, org_id = org
        fake_executor.rows = [
            {"page": "/docs", "value": 42},
            {"page": "/pricing, promo", "value": 7},  # comma must be quoted
        ]
        response = await api_client.post(
            "/api/v1/export",
            json=QUERY,
            headers={**owner, "X-Oriflux-Org": org_id},
        )
        assert response.status_code == 200, response.text
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        lines = response.text.strip().splitlines()
        assert lines[0] == "page,value"
        assert lines[1] == "/docs,42"
        assert lines[2] == '"/pricing, promo",7'

    async def test_export_requires_read_access(self, api_client: httpx.AsyncClient) -> None:
        assert (await api_client.post("/api/v1/export", json=QUERY)).status_code == 401

    async def test_row_cap_is_enforced(
        self,
        api_client: httpx.AsyncClient,
        org: tuple[dict[str, str], str],
        fake_executor: FakeExecutor,
    ) -> None:
        owner, org_id = org
        fake_executor.rows = [{"page": f"/p{i}", "value": i} for i in range(200)]
        response = await api_client.post(
            "/api/v1/export?limit=100",
            json=QUERY,
            headers={**owner, "X-Oriflux-Org": org_id},
        )
        assert len(response.text.strip().splitlines()) == 101  # header + 100


class TestScheduledDumps:
    async def test_enabled_schedules_dump_csv_objects(
        self, db_sessionmaker, fake_executor  # type: ignore[no-untyped-def]
    ) -> None:
        from datetime import UTC, datetime

        from oriflux.db.models import ExportSchedule, Organization
        from oriflux.workers.export_job import run_exports

        async with db_sessionmaker() as session:
            org = Organization(slug="spt", name="SPT")
            session.add(org)
            await session.flush()
            session.add(
                ExportSchedule(
                    org_id=org.id,
                    name="daily-pages",
                    query={"metric": "pageviews", "dimensions": ["page"]},
                )
            )
            await session.commit()
            org_id = org.id

        fake_executor.rows = [{"page": "/docs", "value": 3}]
        written: dict[str, bytes] = {}
        dumped = await run_exports(
            db_sessionmaker,
            fake_executor,
            lambda path, payload: written.update({path: payload}),
            now=datetime(2026, 7, 11, 3, 0, tzinfo=UTC),
        )
        assert dumped == 1
        [(path, payload)] = written.items()
        assert path == f"{org_id}/daily-pages/2026-07-11.csv"
        assert payload.decode().splitlines()[0] == "page,value"
