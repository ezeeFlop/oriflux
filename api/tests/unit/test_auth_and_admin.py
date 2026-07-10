"""Seam: dashboard auth (Google → JWT) and the admin REST surface.

Issue #3 acceptance: org → project → source creatable via /api/v1 with an
ingest key issued per source; Google OAuth + JWT login works; a viewer
cannot administer, an owner can.
"""

import httpx

from tests.unit.conftest import login


class TestGoogleLogin:
    async def test_login_issues_a_jwt_and_me_identifies_the_user(
        self, api_client: httpx.AsyncClient
    ) -> None:
        headers = await login(api_client, "alice")
        me = await api_client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "alice@sponge-theory.io"

    async def test_login_is_idempotent_per_google_account(
        self, api_client: httpx.AsyncClient
    ) -> None:
        first = await api_client.get("/api/v1/me", headers=await login(api_client, "alice"))
        second = await api_client.get("/api/v1/me", headers=await login(api_client, "alice"))
        assert first.json()["id"] == second.json()["id"]

    async def test_invalid_google_token_is_401(self, api_client: httpx.AsyncClient) -> None:
        response = await api_client.post("/api/v1/auth/google", json={"id_token": "forged"})
        assert response.status_code == 401

    async def test_me_without_jwt_is_401(self, api_client: httpx.AsyncClient) -> None:
        assert (await api_client.get("/api/v1/me")).status_code == 401


async def create_org_chain(
    client: httpx.AsyncClient, headers: dict[str, str], slug: str = "sponge-theory"
) -> tuple[str, str, str]:
    """org → project → source; returns their ids."""
    org = await client.post(
        "/api/v1/orgs", json={"slug": slug, "name": slug.title()}, headers=headers
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    project = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"slug": "audigeo", "name": "AudiGEO"},
        headers=headers,
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    source = await client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "web", "name": "audigeo.ai website"},
        headers=headers,
    )
    assert source.status_code == 201, source.text
    return org_id, project_id, source.json()["id"]


class TestAdminChain:
    async def test_org_project_source_and_ingest_key_issuance(
        self, api_client: httpx.AsyncClient
    ) -> None:
        headers = await login(api_client, "alice")
        _, _, source_id = await create_org_chain(api_client, headers)

        issued = await api_client.post(
            f"/api/v1/sources/{source_id}/keys", json={"name": "prod"}, headers=headers
        )
        assert issued.status_code == 201
        body = issued.json()
        assert body["key"].startswith("ofx_ing_")  # plaintext, shown exactly once
        assert body["scope"] == "ingest"

    async def test_org_read_key_issuance(self, api_client: httpx.AsyncClient) -> None:
        headers = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, headers)

        issued = await api_client.post(
            f"/api/v1/orgs/{org_id}/keys", json={"name": "mcp"}, headers=headers
        )
        assert issued.status_code == 201
        assert issued.json()["key"].startswith("ofx_read_")

    async def test_creator_becomes_owner(self, api_client: httpx.AsyncClient) -> None:
        headers = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, headers)
        me = await api_client.get("/api/v1/me", headers=headers)
        assert {"org_id": org_id, "role": "owner"} in me.json()["orgs"]


class TestRbac:
    async def test_a_viewer_cannot_administer_but_an_owner_can(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, project_id, _ = await create_org_chain(api_client, owner)

        added = await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        assert added.status_code == 201

        viewer = await login(api_client, "bob")
        for method, url, payload in [
            ("post", f"/api/v1/orgs/{org_id}/projects", {"slug": "x", "name": "X"}),
            ("post", f"/api/v1/projects/{project_id}/sources", {"type": "web", "name": "x"}),
            ("post", f"/api/v1/orgs/{org_id}/keys", {"name": "x"}),
        ]:
            response = await api_client.request(method, url, json=payload, headers=viewer)
            assert response.status_code == 403, f"{url} should be forbidden to a viewer"

    async def test_a_non_member_cannot_touch_the_org_at_all(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)

        outsider = await login(api_client, "bob")
        response = await api_client.post(
            f"/api/v1/orgs/{org_id}/projects", json={"slug": "x", "name": "X"}, headers=outsider
        )
        assert response.status_code == 403
