"""Seam: goals CRUD + conversion stats over /api/v1 (issue #18).

A goal is declarative — an event name or a page-path prefix. Conversion
counting compiles through the query registry (never bespoke SQL): event
goals filter custom events by event_name, page goals filter pageviews by
url_path prefix; the rate divides by visitors over the same period.
"""

import httpx
import pytest

from tests.unit.conftest import FakeExecutor, login
from tests.unit.test_auth_and_admin import create_org_chain

GOAL_EVENT = {"name": "Signup", "kind": "event", "target": "signup_completed"}
GOAL_PAGE = {"name": "Docs readers", "kind": "page", "target": "/docs/"}
PERIOD = {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"}


@pytest.fixture
async def project(api_client: httpx.AsyncClient) -> tuple[dict[str, str], str, str]:
    owner = await login(api_client, "alice")
    org_id, project_id, _ = await create_org_chain(api_client, owner)
    return owner, org_id, project_id


class TestGoalCrud:
    async def test_admin_creates_lists_deletes(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str]
    ) -> None:
        owner, _, project_id = project
        created = await api_client.post(
            f"/api/v1/projects/{project_id}/goals", json=GOAL_EVENT, headers=owner
        )
        assert created.status_code == 201, created.text
        goal_id = created.json()["id"]

        listed = await api_client.get(
            f"/api/v1/projects/{project_id}/goals", headers=owner
        )
        assert [g["id"] for g in listed.json()] == [goal_id]

        deleted = await api_client.delete(f"/api/v1/goals/{goal_id}", headers=owner)
        assert deleted.status_code == 204

    async def test_viewer_reads_but_cannot_manage(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str]
    ) -> None:
        owner, org_id, project_id = project
        await api_client.post(
            f"/api/v1/projects/{project_id}/goals", json=GOAL_PAGE, headers=owner
        )
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        viewer = await login(api_client, "bob")

        readable = await api_client.get(
            f"/api/v1/projects/{project_id}/goals", headers=viewer
        )
        assert readable.status_code == 200
        assert len(readable.json()) == 1

        forbidden = await api_client.post(
            f"/api/v1/projects/{project_id}/goals", json=GOAL_EVENT, headers=viewer
        )
        assert forbidden.status_code == 403


class TestGoalValidation:
    async def test_event_goal_target_must_be_a_slug(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str]
    ) -> None:
        owner, _, project_id = project
        response = await api_client.post(
            f"/api/v1/projects/{project_id}/goals",
            json={"name": "Bad", "kind": "event", "target": "Not A Slug"},
            headers=owner,
        )
        assert response.status_code == 422

    async def test_page_goal_target_must_be_a_path(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str]
    ) -> None:
        owner, _, project_id = project
        response = await api_client.post(
            f"/api/v1/projects/{project_id}/goals",
            json={"name": "Bad", "kind": "page", "target": "docs"},
            headers=owner,
        )
        assert response.status_code == 422


class TestGoalStats:
    async def test_listing_with_a_period_returns_conversions_and_rate(
        self,
        api_client: httpx.AsyncClient,
        project: tuple[dict[str, str], str, str],
        fake_executor: FakeExecutor,
    ) -> None:
        owner, _, project_id = project
        await api_client.post(
            f"/api/v1/projects/{project_id}/goals", json=GOAL_EVENT, headers=owner
        )
        await api_client.post(
            f"/api/v1/projects/{project_id}/goals", json=GOAL_PAGE, headers=owner
        )
        fake_executor.rows = [{"value": 10}]

        listed = await api_client.get(
            f"/api/v1/projects/{project_id}/goals",
            params=PERIOD,
            headers=owner,
        )
        assert listed.status_code == 200, listed.text
        for goal in listed.json():
            assert goal["conversions"] == 10
            assert goal["conversion_rate"] == 100.0

        executed = " ".join(sql for sql, _ in fake_executor.calls)
        assert "event_name" in executed  # event goal through the registry
        assert "startsWith(url_path" in executed  # page goal through the registry
        # the rate divides unique converting visitors (never raw event counts)
        assert any(
            "uniq(visitor_hash)" in sql and "event_name !=" in sql
            for sql, _ in fake_executor.calls
        )

    async def test_listing_without_a_period_returns_no_stats(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str]
    ) -> None:
        owner, _, project_id = project
        await api_client.post(
            f"/api/v1/projects/{project_id}/goals", json=GOAL_EVENT, headers=owner
        )
        listed = await api_client.get(
            f"/api/v1/projects/{project_id}/goals", headers=owner
        )
        assert listed.json()[0].get("conversions") is None
