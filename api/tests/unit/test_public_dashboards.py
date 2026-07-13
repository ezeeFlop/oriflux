"""Seam: public dashboards via signed share tokens (issue #41, PRD §12).

An admin mints a revocable token (hashed at rest like API keys); the
public path serves only an ALLOW-LISTED metric subset for that project —
rejection is server-side, not UI hiding.
"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import Plan
from oriflux.public.allowlist import PUBLIC_METRICS, is_public_query
from oriflux.query.models import QueryRequest
from tests.unit.conftest import FakeExecutor, login
from tests.unit.test_auth_and_admin import create_org_chain


def q(metric: str, **extra) -> QueryRequest:  # type: ignore[no-untyped-def]
    return QueryRequest.model_validate({
        "metric": metric,
        "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"},
        **extra,
    })


class TestAllowList:
    def test_curated_metrics_pass(self) -> None:
        assert "visitors" in PUBLIC_METRICS
        assert is_public_query(q("visitors", dimensions=["country"]))
        assert is_public_query(q("pageviews", dimensions=["page"]))

    def test_revenue_and_api_internals_are_rejected(self) -> None:
        assert not is_public_query(q("revenue"))
        assert not is_public_query(q("api_error_rate_5xx"))

    def test_non_curated_dimensions_are_rejected(self) -> None:
        assert not is_public_query(q("visitors", dimensions=["class_reason"]))


@pytest.fixture
async def project(api_client: httpx.AsyncClient) -> tuple[dict[str, str], str, str]:
    owner = await login(api_client, "alice")
    org_id, project_id, _ = await create_org_chain(api_client, owner)
    return owner, org_id, project_id


class TestShareTokens:
    async def test_mint_serves_public_then_revoke_blocks(
        self, api_client: httpx.AsyncClient,
        project: tuple[dict[str, str], str, str], fake_executor: FakeExecutor,
    ) -> None:
        owner, _, project_id = project
        minted = await api_client.post(
            f"/api/v1/projects/{project_id}/share", headers=owner
        )
        assert minted.status_code == 201, minted.text
        token = minted.json()["token"]
        assert token.startswith("ofx_pub_")

        fake_executor.rows = [{"country": "FR", "value": 10}]
        public = await api_client.post(
            f"/public/{token}/query",
            json={"metric": "visitors", "dimensions": ["country"],
                  "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"}},
        )
        assert public.status_code == 200, public.text
        assert public.json()["results"] == [{"country": "FR", "value": 10}]
        assert public.headers["x-robots-tag"] == "noindex"

        revoked = await api_client.delete(
            f"/api/v1/share/{minted.json()['id']}", headers=owner
        )
        assert revoked.status_code == 204
        after = await api_client.post(
            f"/public/{token}/query",
            json={"metric": "visitors",
                  "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"}},
        )
        assert after.status_code == 401

    async def test_public_query_outside_the_allowlist_is_rejected(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str],
    ) -> None:
        owner, _, project_id = project
        token = (await api_client.post(
            f"/api/v1/projects/{project_id}/share", headers=owner
        )).json()["token"]
        blocked = await api_client.post(
            f"/public/{token}/query",
            json={"metric": "revenue",
                  "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"}},
        )
        assert blocked.status_code == 403

    async def test_viewer_cannot_mint(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str],
    ) -> None:
        owner, org_id, project_id = project
        await api_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": "bob@sponge-theory.io", "role": "viewer"}, headers=owner,
        )
        viewer = await login(api_client, "bob")
        forbidden = await api_client.post(
            f"/api/v1/projects/{project_id}/share", headers=viewer
        )
        assert forbidden.status_code == 403


class TestPublicPricing:
    async def test_pricing_is_unauthenticated_and_reflects_stripe_amounts(
        self,
        api_client: httpx.AsyncClient,
        db_sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with db_sessionmaker() as session:
            session.add(Plan(slug="free", name="Free", monthly_events=100_000))
            session.add(Plan(
                slug="pro", name="Pro", monthly_events=1_000_000,
                stripe_price_id="price_pro", stripe_price_id_annual="price_pro_yr",
                amount_cents=1900, amount_cents_annual=19000, currency="eur",
            ))
            session.add(Plan(slug="internal", name="Internal", monthly_events=None))
            await session.commit()

        # no Authorization header at all
        response = await api_client.get("/api/v1/pricing")
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
        by_slug = {p["slug"]: p for p in response.json()}
        assert "internal" not in by_slug  # dogfooding plan never public
        assert by_slug["pro"]["amount_cents"] == 1900
        assert by_slug["pro"]["amount_cents_annual"] == 19000
        assert by_slug["pro"]["currency"] == "eur"
        assert by_slug["free"]["amount_cents"] is None  # no hardcoded 0
        assert by_slug["pro"]["subscribable"] is True
