"""Seam: Stripe billing endpoints + the idempotent webhook (issue #63).

The gateway is faked for hosted URLs; webhook signatures go through the
REAL verification path (shared HMAC scheme) with fixtures signed by the
same helper — no network, no stripe.com.
"""

import json
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.api.main import create_app
from oriflux.billing import CheckoutRequest, StripeGateway, sign_stripe_payload
from oriflux.db.models import Organization, Plan
from tests.unit.conftest import TEST_SETTINGS, FakeExecutor, FakeGoogle, login
from tests.unit.test_auth_and_admin import create_org_chain

WEBHOOK_SECRET = "whsec_test_secret"


class FakeStripeGateway(StripeGateway):
    """Real signature verification, fake hosted sessions."""

    def __init__(self) -> None:
        super().__init__("sk_test_fake", WEBHOOK_SECRET)
        self.checkouts: list[CheckoutRequest] = []

    def create_checkout(self, request: CheckoutRequest) -> str:
        self.checkouts.append(request)
        return f"https://checkout.stripe.test/{request.plan_slug}"

    def create_portal(self, customer_id: str, return_url: str) -> str:
        return f"https://portal.stripe.test/{customer_id}"


@pytest.fixture
def gateway() -> FakeStripeGateway:
    return FakeStripeGateway()


@pytest.fixture
async def billing_client(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    fake_executor: FakeExecutor,
    gateway: FakeStripeGateway,
) -> AsyncIterator[httpx.AsyncClient]:
    from fakeredis import FakeAsyncRedis

    app = create_app(
        executor=fake_executor,
        settings=TEST_SETTINGS,
        session_factory=db_sessionmaker,
        google_verifier=FakeGoogle(),
        redis=FakeAsyncRedis(),
        billing_gateway=gateway,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


async def seed_pro_plan(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        session.add(Plan(slug="pro", name="Pro", monthly_events=1_000_000,
                         stripe_price_id="price_pro_1"))
        session.add(Plan(slug="free", name="Free", monthly_events=100_000))
        await session.commit()


def signed(event: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    payload = json.dumps(event).encode()
    return payload, {
        "stripe-signature": sign_stripe_payload(payload, WEBHOOK_SECRET),
        "content-type": "application/json",
    }


class TestBillingEndpoints:
    async def test_checkout_uses_the_plan_price_and_returns_the_hosted_url(
        self,
        billing_client: httpx.AsyncClient,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        gateway: FakeStripeGateway,
    ) -> None:
        await seed_pro_plan(db_sessionmaker)
        owner = await login(billing_client, "alice")
        org_id, _, _ = await create_org_chain(billing_client, owner)

        response = await billing_client.post(
            f"/api/v1/orgs/{org_id}/billing/checkout",
            json={"plan_slug": "pro"},
            headers=owner,
        )
        assert response.status_code == 200, response.text
        assert response.json()["url"] == "https://checkout.stripe.test/pro"
        assert gateway.checkouts[0].price_id == "price_pro_1"
        assert gateway.checkouts[0].org_id == org_id

    async def test_checkout_rejects_a_plan_without_price(
        self,
        billing_client: httpx.AsyncClient,
        db_sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        await seed_pro_plan(db_sessionmaker)
        owner = await login(billing_client, "alice")
        org_id, _, _ = await create_org_chain(billing_client, owner)
        response = await billing_client.post(
            f"/api/v1/orgs/{org_id}/billing/checkout",
            json={"plan_slug": "free"},
            headers=owner,
        )
        assert response.status_code == 422

    async def test_disabled_instance_answers_503_and_reports_disabled(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        fake_executor: FakeExecutor,
    ) -> None:
        from fakeredis import FakeAsyncRedis

        app = create_app(
            executor=fake_executor,
            settings=TEST_SETTINGS,  # no stripe keys → StripeGateway disabled
            session_factory=db_sessionmaker,
            google_verifier=FakeGoogle(),
            redis=FakeAsyncRedis(),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api"
        ) as client:
            owner = await login(client, "alice")
            org_id, _, _ = await create_org_chain(client, owner)
            state = await client.get(f"/api/v1/orgs/{org_id}/billing", headers=owner)
            assert state.status_code == 200
            assert state.json()["enabled"] is False
            checkout = await client.post(
                f"/api/v1/orgs/{org_id}/billing/checkout",
                json={"plan_slug": "pro"},
                headers=owner,
            )
            assert checkout.status_code == 503


class TestWebhook:
    async def test_checkout_completed_sets_plan_and_customer_idempotently(
        self,
        billing_client: httpx.AsyncClient,
        db_sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        await seed_pro_plan(db_sessionmaker)
        owner = await login(billing_client, "alice")
        org_id, _, _ = await create_org_chain(billing_client, owner)

        payload, headers = signed({
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": org_id,
                "customer": "cus_123",
                "metadata": {"org_id": org_id, "plan_slug": "pro"},
            }},
        })
        first = await billing_client.post(
            "/api/v1/billing/webhook", content=payload, headers=headers
        )
        assert first.status_code == 200 and first.json()["duplicate"] is False

        async with db_sessionmaker() as session:
            org = await session.get(Organization, uuid.UUID(org_id))
            assert org is not None
            assert org.plan_slug == "pro"
            assert org.stripe_customer_id == "cus_123"

        replay = await billing_client.post(
            "/api/v1/billing/webhook", content=payload, headers=headers
        )
        assert replay.json()["duplicate"] is True

    async def test_subscription_deleted_downgrades_to_free(
        self,
        billing_client: httpx.AsyncClient,
        db_sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        await seed_pro_plan(db_sessionmaker)
        owner = await login(billing_client, "alice")
        org_id, _, _ = await create_org_chain(billing_client, owner)
        async with db_sessionmaker() as session:
            org = await session.get(Organization, uuid.UUID(org_id))
            assert org is not None
            org.plan_slug = "pro"
            org.stripe_customer_id = "cus_del"
            await session.commit()

        payload, headers = signed({
            "id": "evt_2",
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_del", "metadata": {}}},
        })
        response = await billing_client.post(
            "/api/v1/billing/webhook", content=payload, headers=headers
        )
        assert response.status_code == 200
        async with db_sessionmaker() as session:
            org = (
                await session.execute(
                    select(Organization).where(Organization.stripe_customer_id == "cus_del")
                )
            ).scalar_one()
            assert org.plan_slug == "free"

    async def test_bad_signature_is_400(
        self, billing_client: httpx.AsyncClient
    ) -> None:
        response = await billing_client.post(
            "/api/v1/billing/webhook",
            content=b'{"id": "evt_x"}',
            headers={"stripe-signature": "t=1,v1=forged", "content-type": "application/json"},
        )
        assert response.status_code == 400
