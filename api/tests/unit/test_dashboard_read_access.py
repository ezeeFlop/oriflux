"""Seam: dashboard read access (issue #7).

/api/v1/query serves two callers: API consumers with a read key (org
implied by the key) and dashboard users with a JWT + X-Oriflux-Org header
(org verified against their membership, viewer is enough). The switcher
needs GET /orgs/{org_id}/projects.
"""

import httpx

from tests.unit.conftest import login
from tests.unit.test_auth_and_admin import create_org_chain

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}
VALID = {"metric": "pageviews", "period": JULY}


class TestJwtQueryAccess:
    async def test_a_member_queries_their_org_with_a_jwt(
        self, api_client: httpx.AsyncClient
    ) -> None:
        headers = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, headers)
        response = await api_client.post(
            "/api/v1/query", json=VALID, headers={**headers, "X-Oriflux-Org": org_id}
        )
        assert response.status_code == 200, response.text

    async def test_a_jwt_without_the_org_header_is_400(
        self, api_client: httpx.AsyncClient
    ) -> None:
        headers = await login(api_client, "alice")
        await create_org_chain(api_client, headers)
        response = await api_client.post("/api/v1/query", json=VALID, headers=headers)
        assert response.status_code == 400

    async def test_a_non_member_cannot_query_the_org(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        outsider = await login(api_client, "bob")
        response = await api_client.post(
            "/api/v1/query", json=VALID, headers={**outsider, "X-Oriflux-Org": org_id}
        )
        assert response.status_code == 403

    async def test_a_viewer_can_query(self, api_client: httpx.AsyncClient) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        viewer = await login(api_client, "bob")
        response = await api_client.post(
            "/api/v1/query", json=VALID, headers={**viewer, "X-Oriflux-Org": org_id}
        )
        assert response.status_code == 200


class TestProjectListing:
    async def test_members_list_projects_for_the_switcher(
        self, api_client: httpx.AsyncClient
    ) -> None:
        headers = await login(api_client, "alice")
        org_id, project_id, _ = await create_org_chain(api_client, headers)
        response = await api_client.get(
            f"/api/v1/orgs/{org_id}/projects", headers=headers
        )
        assert response.status_code == 200
        assert [p["id"] for p in response.json()] == [project_id]
