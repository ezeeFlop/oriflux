"""Seam: alert-rule CRUD over /api/v1 (issue #11) — RBAC + validation."""

import httpx
import pytest

from tests.unit.conftest import login
from tests.unit.test_auth_and_admin import create_org_chain

RULE = {
    "name": "5xx over 2%",
    "metric": "api_error_rate_5xx",
    "condition": "gt",
    "threshold": 2.0,
    "window_minutes": 5,
}


@pytest.fixture
async def org(api_client: httpx.AsyncClient) -> tuple[dict[str, str], str]:
    owner = await login(api_client, "alice")
    org_id, _, _ = await create_org_chain(api_client, owner)
    return owner, org_id


class TestRuleCrud:
    async def test_admin_creates_lists_patches_deletes(
        self, api_client: httpx.AsyncClient, org: tuple[dict[str, str], str]
    ) -> None:
        owner, org_id = org
        created = await api_client.post(
            f"/api/v1/orgs/{org_id}/alert-rules", json=RULE, headers=owner
        )
        assert created.status_code == 201, created.text
        rule_id = created.json()["id"]

        listed = await api_client.get(f"/api/v1/orgs/{org_id}/alert-rules", headers=owner)
        assert [r["id"] for r in listed.json()] == [rule_id]

        patched = await api_client.patch(
            f"/api/v1/alert-rules/{rule_id}", json={"enabled": False}, headers=owner
        )
        assert patched.json()["enabled"] is False

        deleted = await api_client.delete(f"/api/v1/alert-rules/{rule_id}", headers=owner)
        assert deleted.status_code == 204

    async def test_viewer_reads_but_cannot_manage(
        self, api_client: httpx.AsyncClient, org: tuple[dict[str, str], str]
    ) -> None:
        owner, org_id = org
        await api_client.post(f"/api/v1/orgs/{org_id}/alert-rules", json=RULE, headers=owner)
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        viewer = await login(api_client, "bob")

        readable = await api_client.get(
            f"/api/v1/orgs/{org_id}/alert-rules", headers=viewer
        )
        assert readable.status_code == 200
        assert len(readable.json()) == 1

        forbidden = await api_client.post(
            f"/api/v1/orgs/{org_id}/alert-rules", json=RULE, headers=viewer
        )
        assert forbidden.status_code == 403

        events = await api_client.get(f"/api/v1/orgs/{org_id}/alert-events", headers=viewer)
        assert events.status_code == 200


class TestRuleValidation:
    async def test_unknown_metric_is_rejected_via_the_registry(
        self, api_client: httpx.AsyncClient, org: tuple[dict[str, str], str]
    ) -> None:
        owner, org_id = org
        response = await api_client.post(
            f"/api/v1/orgs/{org_id}/alert-rules",
            json={**RULE, "metric": "profit_margin"},
            headers=owner,
        )
        assert response.status_code == 422
        assert "available" in response.json()["detail"]

    async def test_ssrf_webhook_urls_are_rejected(
        self, api_client: httpx.AsyncClient, org: tuple[dict[str, str], str]
    ) -> None:
        owner, org_id = org
        for url in ("https://169.254.169.254/x", "http://hooks.slack.com/x"):
            response = await api_client.post(
                f"/api/v1/orgs/{org_id}/alert-rules",
                json={**RULE, "slack_webhook_url": url},
                headers=owner,
            )
            assert response.status_code == 422, url


class TestRuleProjectScope:
    async def test_project_filter_becomes_the_rule_scope_on_events(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """#47/#52: a rule filtered on a project carries that project on
        its listing so alert events can deep-link back to it."""
        owner = await login(api_client, "alice")
        org_id, project_id, _ = await create_org_chain(api_client, owner)
        created = await api_client.post(
            f"/api/v1/orgs/{org_id}/alert-rules",
            json={
                "name": "5xx spike",
                "metric": "api_error_rate_5xx",
                "filters": [{"dimension": "project_id", "op": "eq", "value": project_id}],
                "condition": "gt",
                "threshold": 5,
            },
            headers=owner,
        )
        assert created.status_code == 201, created.text
