"""Seam: dashboard auth (Google → JWT) and the admin REST surface.

Issue #3 acceptance: org → project → source creatable via /api/v1 with an
ingest key issued per source; Google OAuth + JWT login works; a viewer
cannot administer, an owner can.
"""

import uuid as _uuid

import httpx

from tests.unit.conftest import login


def uuid_of(value: str) -> _uuid.UUID:
    return _uuid.UUID(value)


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


class TestAdminListing:
    """Issue #45: the settings UI needs to list what the POSTs created."""

    async def test_project_sources_are_listable(self, api_client: httpx.AsyncClient) -> None:
        owner = await login(api_client, "alice")
        _, project_id, source_id = await create_org_chain(api_client, owner)

        listed = await api_client.get(f"/api/v1/projects/{project_id}/sources", headers=owner)
        assert listed.status_code == 200
        sources = listed.json()
        assert [s["id"] for s in sources] == [source_id]
        assert sources[0]["type"] == "web"
        assert sources[0]["name"] == "audigeo.ai website"

    async def test_org_keys_listing_shows_prefix_and_revocation_never_secrets(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, source_id = await create_org_chain(api_client, owner)
        ingest = await api_client.post(
            f"/api/v1/sources/{source_id}/keys", json={"name": "site"}, headers=owner
        )
        read = await api_client.post(
            f"/api/v1/orgs/{org_id}/keys", json={"name": "mcp"}, headers=owner
        )
        assert ingest.status_code == 201 and read.status_code == 201

        listed = await api_client.get(f"/api/v1/orgs/{org_id}/keys", headers=owner)
        assert listed.status_code == 200
        keys = {k["id"]: k for k in listed.json()}
        assert set(keys) == {ingest.json()["id"], read.json()["id"]}

        ingest_row = keys[ingest.json()["id"]]
        assert ingest_row["scope"] == "ingest"
        assert ingest_row["source_id"] == source_id
        assert ingest_row["key_prefix"] == ingest.json()["key_prefix"]
        assert ingest_row["revoked"] is False
        # the plaintext and the hash must never appear in a listing
        assert "key" not in ingest_row and "key_hash" not in ingest_row

        revoked = await api_client.delete(
            f"/api/v1/keys/{read.json()['id']}", headers=owner
        )
        assert revoked.status_code == 204
        relisted = await api_client.get(f"/api/v1/orgs/{org_id}/keys", headers=owner)
        assert {k["id"]: k["revoked"] for k in relisted.json()}[read.json()["id"]] is True

    async def test_a_viewer_cannot_list_keys_but_can_list_sources(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, project_id, _ = await create_org_chain(api_client, owner)
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        viewer = await login(api_client, "bob")
        assert (
            await api_client.get(f"/api/v1/projects/{project_id}/sources", headers=viewer)
        ).status_code == 200
        assert (
            await api_client.get(f"/api/v1/orgs/{org_id}/keys", headers=viewer)
        ).status_code == 403


class TestMembersAndSharesListing:
    """Issue #46: members and share links need list endpoints for the UI."""

    async def test_members_are_listable_with_email_and_role(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        listed = await api_client.get(f"/api/v1/orgs/{org_id}/members", headers=owner)
        assert listed.status_code == 200
        members = {m["email"]: m["role"] for m in listed.json()}
        assert members == {"alice@sponge-theory.io": "owner", "bob@sponge-theory.io": "viewer"}

    async def test_members_listing_is_open_to_members_only(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        outsider = await login(api_client, "bob")
        assert (
            await api_client.get(f"/api/v1/orgs/{org_id}/members", headers=outsider)
        ).status_code == 403

    async def test_shares_are_listable_with_revocation_state_and_no_token(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, project_id, _ = await create_org_chain(api_client, owner)
        minted = await api_client.post(f"/api/v1/projects/{project_id}/share", headers=owner)
        assert minted.status_code == 201
        share_id = minted.json()["id"]

        listed = await api_client.get(f"/api/v1/projects/{project_id}/shares", headers=owner)
        assert listed.status_code == 200
        rows = listed.json()
        assert [r["id"] for r in rows] == [share_id]
        assert rows[0]["revoked"] is False
        assert "token" not in rows[0] and "token_hash" not in rows[0]

        await api_client.delete(f"/api/v1/share/{share_id}", headers=owner)
        relisted = await api_client.get(f"/api/v1/projects/{project_id}/shares", headers=owner)
        assert relisted.json()[0]["revoked"] is True

        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        viewer = await login(api_client, "bob")
        assert (
            await api_client.get(f"/api/v1/projects/{project_id}/shares", headers=viewer)
        ).status_code == 403


class TestUsage:
    """Issue #61: plan and monthly consumption are visible to any member."""

    async def test_usage_reports_plan_quota_and_counter(
        self, api_client: httpx.AsyncClient
    ) -> None:
        from datetime import UTC, datetime

        from oriflux.db.models import Plan

        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)

        # seed a plan + point the org at it + a live Redis counter
        transport = api_client._transport  # type: ignore[attr-defined]
        app = transport.app  # type: ignore[attr-defined]
        async with app.state.session_factory() as session:
            from sqlalchemy import update

            from oriflux.db.models import Organization

            session.add(Plan(slug="pro-test", name="Pro", monthly_events=1000))
            await session.execute(
                update(Organization)
                .where(Organization.id == uuid_of(org_id))
                .values(plan_slug="pro-test")
            )
            await session.commit()
        month = f"{datetime.now(tz=UTC):%Y%m}"
        await app.state.redis.set(f"oriflux:quota:{org_id}:{month}", 250)

        usage = await api_client.get(f"/api/v1/orgs/{org_id}/usage", headers=owner)
        assert usage.status_code == 200, usage.text
        body = usage.json()
        assert body["plan_slug"] == "pro-test"
        assert body["plan_name"] == "Pro"
        assert body["monthly_events"] == 1000
        assert body["used"] == 250
        assert body["pct"] == 25.0

    async def test_usage_on_unlimited_plan_has_no_pct(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        usage = await api_client.get(f"/api/v1/orgs/{org_id}/usage", headers=owner)
        assert usage.status_code == 200
        body = usage.json()
        # default plan_slug is free but no plans row is seeded in unit schema
        assert body["monthly_events"] is None
        assert body["pct"] is None
        assert body["used"] == 0
