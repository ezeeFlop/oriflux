"""Seam: POST /api/v1/funnel (issue #19) — read access, typed request."""

import httpx
import pytest

from tests.unit.conftest import FakeExecutor, login
from tests.unit.test_auth_and_admin import create_org_chain

FUNNEL = {
    "steps": [
        {"kind": "page", "target": "/pricing"},
        {"kind": "event", "target": "signup_completed"},
    ],
    "scope": "session",
    "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"},
}


@pytest.fixture
async def org(api_client: httpx.AsyncClient) -> tuple[dict[str, str], str]:
    owner = await login(api_client, "alice")
    org_id, _, _ = await create_org_chain(api_client, owner)
    return owner, org_id


class TestFunnelEndpoint:
    async def test_funnel_returns_per_step_counts_and_conversion(
        self,
        api_client: httpx.AsyncClient,
        org: tuple[dict[str, str], str],
        fake_executor: FakeExecutor,
    ) -> None:
        owner, org_id = org
        fake_executor.rows = [{"step_1": 30, "step_2": 12}]

        response = await api_client.post(
            "/api/v1/funnel",
            json=FUNNEL,
            headers={**owner, "X-Oriflux-Org": org_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["scope"] == "session"  # the UI labels session-scoped funnels
        assert body["steps"] == [
            {"step": 1, "target": "/pricing", "entered": 30},
            {"step": 2, "target": "signup_completed", "entered": 12},
        ]
        assert body["conversion_rate"] == 40.0

        executed, _ = fake_executor.calls[0]
        assert "windowFunnel" in executed
        assert "org_id" in executed

    async def test_invalid_window_for_the_scope_is_rejected(
        self, api_client: httpx.AsyncClient, org: tuple[dict[str, str], str]
    ) -> None:
        owner, org_id = org
        response = await api_client.post(
            "/api/v1/funnel",
            json={**FUNNEL, "window_hours": 48},
            headers={**owner, "X-Oriflux-Org": org_id},
        )
        assert response.status_code == 422

    async def test_requires_read_access(self, api_client: httpx.AsyncClient) -> None:
        response = await api_client.post("/api/v1/funnel", json=FUNNEL)
        assert response.status_code == 401
