"""Seam: Stripe / Lemon Squeezy revenue connectors (issue #24, PRD §5.4).

Webhooks are signature-verified, idempotent under redelivery (the event
UUID derives deterministically from the provider event id, so ClickHouse
dedup absorbs duplicates), and secrets are Fernet-encrypted at rest.
"""

import hashlib
import hmac
import json
import time
import uuid as _uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings
from oriflux.connectors.revenue import (
    map_lemonsqueezy_event,
    map_stripe_event,
    verify_lemonsqueezy_signature,
    verify_stripe_signature,
)
from oriflux.db.models import Connector, ConnectorProvider, Organization, Project
from oriflux.ingest.main import create_app
from oriflux.models.events import EnrichedEvent
from oriflux.security.secrets import decrypt_secret, encrypt_secret, generate_fernet_key
from oriflux.storage.redis_stream import EVENTS_STREAM

SECRET = "whsec_test_123"


def stripe_headers(payload: bytes, secret: str = SECRET) -> str:
    ts = int(time.time())
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


class TestSignatures:
    def test_valid_stripe_signature_passes(self) -> None:
        payload = b'{"id":"evt_1"}'
        assert verify_stripe_signature(payload, stripe_headers(payload), SECRET)

    def test_tampered_stripe_payload_fails(self) -> None:
        header = stripe_headers(b'{"id":"evt_1"}')
        assert not verify_stripe_signature(b'{"id":"evt_EVIL"}', header, SECRET)

    def test_lemonsqueezy_signature_roundtrip(self) -> None:
        payload = b'{"meta":{}}'
        signature = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_lemonsqueezy_signature(payload, signature, SECRET)
        assert not verify_lemonsqueezy_signature(payload, "deadbeef", SECRET)


class TestStripeMapping:
    def test_subscription_created_maps_to_a_revenue_event(self) -> None:
        event = map_stripe_event(
            {
                "id": "evt_123",
                "type": "customer.subscription.created",
                "data": {"object": {"plan": {"amount": 4900, "currency": "eur",
                                             "nickname": "pro"}}},
            }
        )
        assert event is not None
        assert event.name == "revenue_subscription_created"
        assert event.amount == 49.0
        assert event.props["provider"] == "stripe"
        assert event.props["currency"] == "eur"

    def test_subscription_deleted_is_churn(self) -> None:
        event = map_stripe_event(
            {
                "id": "evt_124",
                "type": "customer.subscription.deleted",
                "data": {"object": {"plan": {"amount": 4900, "currency": "eur"}}},
            }
        )
        assert event is not None
        assert event.name == "revenue_churn"
        assert event.amount == -49.0

    def test_unrelated_event_types_map_to_none(self) -> None:
        assert map_stripe_event({"id": "evt_1", "type": "charge.updated", "data": {}}) is None

    def test_redelivery_yields_the_same_event_uuid(self) -> None:
        payload = {
            "id": "evt_123",
            "type": "customer.subscription.created",
            "data": {"object": {"plan": {"amount": 100, "currency": "eur"}}},
        }
        first, second = map_stripe_event(payload), map_stripe_event(payload)
        assert first is not None and second is not None
        assert first.event_id == second.event_id  # ClickHouse dedup absorbs redelivery


class TestLemonSqueezyMapping:
    def test_subscription_created(self) -> None:
        event = map_lemonsqueezy_event(
            {
                "meta": {"event_name": "subscription_created",
                         "webhook_id": "wh_1"},
                "data": {"attributes": {"total": 1900, "currency": "EUR",
                                        "variant_name": "starter"}},
            }
        )
        assert event is not None
        assert event.name == "revenue_subscription_created"
        assert event.amount == 19.0
        assert event.props["provider"] == "lemonsqueezy"


class TestFernetSecrets:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        key = generate_fernet_key()
        token = encrypt_secret("whsec_super", key)
        assert token != "whsec_super"
        assert decrypt_secret(token, key) == "whsec_super"


FERNET_KEY = generate_fernet_key()


@pytest.fixture
async def connector_ids(db_sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    async with db_sessionmaker() as session:
        org = Organization(slug="spt", name="SPT")
        session.add(org)
        await session.flush()
        project = Project(org_id=org.id, slug="cliphaven", name="ClipHaven")
        session.add(project)
        await session.flush()
        connector = Connector(
            org_id=org.id,
            project_id=project.id,
            provider=ConnectorProvider.stripe,
            webhook_secret_encrypted=encrypt_secret(SECRET, FERNET_KEY),
        )
        session.add(connector)
        await session.commit()
        return str(connector.id)


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()


@pytest.fixture
async def ingest_client(
    redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_key_cache_ttl_s=0.0, fernet_key=FERNET_KEY)
    app = create_app(redis=redis, settings=settings, session_factory=db_sessionmaker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as c:
        yield c


STRIPE_PAYLOAD = json.dumps(
    {
        "id": "evt_hook_1",
        "type": "customer.subscription.created",
        "data": {"object": {"plan": {"amount": 4900, "currency": "eur", "nickname": "pro"}}},
    }
).encode()


class TestWebhookEndpoint:
    async def test_signed_stripe_webhook_lands_a_revenue_event(
        self, ingest_client: httpx.AsyncClient, redis: FakeAsyncRedis, connector_ids: str
    ) -> None:
        response = await ingest_client.post(
            f"/api/v1/connectors/{connector_ids}/webhook",
            content=STRIPE_PAYLOAD,
            headers={"Stripe-Signature": stripe_headers(STRIPE_PAYLOAD)},
        )
        assert response.status_code == 202, response.text
        entries = await redis.xrange(EVENTS_STREAM)
        assert len(entries) == 1
        event = EnrichedEvent.model_validate_json(entries[0][1][b"payload"])
        assert event.event_name == "revenue_subscription_created"
        assert event.value == 49.0
        assert event.source_type == "api"

    async def test_bad_signature_is_rejected(
        self, ingest_client: httpx.AsyncClient, redis: FakeAsyncRedis, connector_ids: str
    ) -> None:
        response = await ingest_client.post(
            f"/api/v1/connectors/{connector_ids}/webhook",
            content=STRIPE_PAYLOAD,
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
        assert response.status_code == 401
        assert await redis.xlen(EVENTS_STREAM) == 0

    async def test_unknown_connector_is_404(
        self, ingest_client: httpx.AsyncClient
    ) -> None:
        response = await ingest_client.post(
            f"/api/v1/connectors/{_uuid.uuid4()}/webhook",
            content=STRIPE_PAYLOAD,
            headers={"Stripe-Signature": stripe_headers(STRIPE_PAYLOAD)},
        )
        assert response.status_code == 404
