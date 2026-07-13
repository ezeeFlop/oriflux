"""Stripe billing gateway (issue #63, PRD #59).

Thin, injectable wrapper around the Stripe SDK so the endpoints and the
webhook are testable without any network call. Prices live on the plans
table (stripe_price_id) — no amount is ever hardcoded. With no secret key
configured the gateway reports disabled and the instance runs entirely on
the free/internal plans.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol


class BillingDisabled(Exception):
    pass


class InvalidSignature(Exception):
    pass


@dataclass
class CheckoutRequest:
    org_id: str
    customer_id: str | None
    customer_email: str
    price_id: str
    plan_slug: str
    success_url: str
    cancel_url: str


@dataclass
class PriceInfo:
    """A Stripe price's public facts — the amount is never authored here, it
    is read back from Stripe so the displayed price is always the real one."""

    amount_cents: int
    currency: str
    interval: str  # "month" | "year"


class BillingGateway(Protocol):
    @property
    def enabled(self) -> bool: ...

    def create_checkout(self, request: CheckoutRequest) -> str:
        """Returns the hosted checkout URL."""
        ...

    def create_portal(self, customer_id: str, return_url: str) -> str:
        """Returns the hosted customer-portal URL."""
        ...

    def get_price(self, price_id: str) -> PriceInfo | None:
        """Read a price's amount/currency/interval from Stripe (None if the
        price is unknown or billing is disabled)."""
        ...

    def parse_webhook(self, payload: bytes, signature_header: str) -> dict[str, Any]:
        """Verify the signature and return the event dict."""
        ...


class StripeGateway:
    """Production gateway; imports stripe lazily so disabled instances never
    touch the SDK."""

    def __init__(self, secret_key: str, webhook_secret: str) -> None:
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret

    @property
    def enabled(self) -> bool:
        return self._secret_key != ""

    def _client(self) -> Any:
        import stripe

        stripe.api_key = self._secret_key
        return stripe

    def create_checkout(self, request: CheckoutRequest) -> str:
        stripe = self._client()
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": request.price_id, "quantity": 1}],
            client_reference_id=request.org_id,
            customer=request.customer_id,
            customer_email=None if request.customer_id else request.customer_email,
            metadata={"org_id": request.org_id, "plan_slug": request.plan_slug},
            subscription_data={
                "metadata": {"org_id": request.org_id, "plan_slug": request.plan_slug}
            },
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return str(session.url)

    def create_portal(self, customer_id: str, return_url: str) -> str:
        stripe = self._client()
        session = stripe.billing_portal.Session.create(
            customer=customer_id, return_url=return_url
        )
        return str(session.url)

    def get_price(self, price_id: str) -> PriceInfo | None:
        if not self.enabled:
            return None
        stripe = self._client()
        price = stripe.Price.retrieve(price_id)
        amount = price.get("unit_amount")
        recurring = price.get("recurring") or {}
        if amount is None:
            return None
        return PriceInfo(
            amount_cents=int(amount),
            currency=str(price.get("currency", "eur")),
            interval=str(recurring.get("interval", "month")),
        )

    def parse_webhook(self, payload: bytes, signature_header: str) -> dict[str, Any]:
        if not verify_stripe_signature(payload, signature_header, self._webhook_secret):
            raise InvalidSignature("bad stripe signature")
        return dict(json.loads(payload))


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, *, tolerance_s: int = 300
) -> bool:
    """Stripe's t=…,v1=… scheme, implemented directly so the fake gateway in
    tests and the real one share the exact verification path."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        expected = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(time.time() - timestamp) > tolerance_s:
        return False
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


def sign_stripe_payload(payload: bytes, secret: str, *, timestamp: int | None = None) -> str:
    """Build a valid signature header — used by tests to play fixtures."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"
