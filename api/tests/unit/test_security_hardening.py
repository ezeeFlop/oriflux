"""Regression tests for the issue #3 security-review findings."""

from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.security.google import GoogleVerificationError, make_google_verifier
from tests.unit.conftest import login
from tests.unit.test_auth_and_admin import create_org_chain
from tests.unit.test_ingest_auth import VALID_EVENT, Seeded, auth, make_client, seed


class TestUnauthenticatedFloodIsMetered:
    async def test_random_key_requests_hit_the_per_ip_limit(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Invalid keys must be rate-limited BEFORE touching PostgreSQL."""
        redis = FakeAsyncRedis()
        async with make_client(redis, db_sessionmaker, ingest_rate_limit_per_ip=2) as client:
            for i in range(2):
                response = await client.post(
                    "/api/v1/events", json=VALID_EVENT, headers=auth(f"ofx_ing_junk{i}")
                )
                assert response.status_code == 401
            throttled = await client.post(
                "/api/v1/events", json=VALID_EVENT, headers=auth("ofx_ing_junk999")
            )
            assert throttled.status_code == 429

    async def test_spoofed_leftmost_forwarded_for_does_not_reset_the_budget(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Only the proxy-appended (rightmost) X-Forwarded-For hop counts."""
        seeded: Seeded = await seed(db_sessionmaker)
        redis = FakeAsyncRedis()
        async with make_client(redis, db_sessionmaker, ingest_rate_limit_per_ip=1) as client:
            first = await client.post(
                "/api/v1/events",
                json=VALID_EVENT,
                headers={**auth(seeded.ingest_key), "X-Forwarded-For": "6.6.6.1, 10.0.0.9"},
            )
            assert first.status_code == 202
            spoofed = await client.post(
                "/api/v1/events",
                json=VALID_EVENT,
                headers={**auth(seeded.ingest_key), "X-Forwarded-For": "6.6.6.2, 10.0.0.9"},
            )
            assert spoofed.status_code == 429


class TestOwnerRoleProtection:
    async def test_an_admin_cannot_mint_or_demote_owners(
        self, api_client: httpx.AsyncClient
    ) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "admin"},
            headers=owner,
        )
        admin = await login(api_client, "bob")

        mint = await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "eve@sponge-theory.io", "role": "owner"},
            headers=admin,
        )
        assert mint.status_code == 403

        demote = await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "alice@sponge-theory.io", "role": "viewer"},
            headers=admin,
        )
        assert demote.status_code == 403

    async def test_the_owner_can_grant_owner(self, api_client: httpx.AsyncClient) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        response = await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "owner"},
            headers=owner,
        )
        assert response.status_code == 201


class TestKeyRevocationEndpoint:
    async def test_a_revoked_read_key_stops_working(self, api_client: httpx.AsyncClient) -> None:
        headers = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, headers)
        issued = (
            await api_client.post(
                f"/api/v1/orgs/{org_id}/keys", json={"name": "x"}, headers=headers
            )
        ).json()

        query = {"metric": "pageviews", "period": {
            "start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}}
        before = await api_client.post(
            "/api/v1/query", json=query, headers={"Authorization": f"Bearer {issued['key']}"}
        )
        assert before.status_code == 200

        revoked = await api_client.delete(f"/api/v1/keys/{issued['id']}", headers=headers)
        assert revoked.status_code == 204

        after = await api_client.post(
            "/api/v1/query", json=query, headers={"Authorization": f"Bearer {issued['key']}"}
        )
        assert after.status_code == 401

    async def test_a_viewer_cannot_revoke(self, api_client: httpx.AsyncClient) -> None:
        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        issued = (
            await api_client.post(
                f"/api/v1/orgs/{org_id}/keys", json={"name": "x"}, headers=owner
            )
        ).json()
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"},
            headers=owner,
        )
        viewer = await login(api_client, "bob")
        response = await api_client.delete(f"/api/v1/keys/{issued['id']}", headers=viewer)
        assert response.status_code == 403


class TestGoogleEmailVerification:
    def _verifier_with_claims(
        self, monkeypatch: pytest.MonkeyPatch, claims: dict[str, Any]
    ) -> Any:
        from google.oauth2 import id_token

        monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: claims)
        return make_google_verifier("client-id")

    def test_unverified_email_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        verify = self._verifier_with_claims(
            monkeypatch,
            {"sub": "s", "email": "eve@evil.io", "email_verified": False},
        )
        with pytest.raises(GoogleVerificationError, match="email not verified"):
            verify("token")

    def test_verified_email_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        verify = self._verifier_with_claims(
            monkeypatch,
            {"sub": "s", "email": "alice@sponge-theory.io", "email_verified": True},
        )
        assert verify("token").email == "alice@sponge-theory.io"
