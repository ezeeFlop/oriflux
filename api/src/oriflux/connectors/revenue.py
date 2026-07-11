"""Provider webhooks → revenue events (issue #24, PRD §5.4).

Each mapped event carries a DETERMINISTIC uuid5 derived from the provider
event id: redeliveries produce the same event_id and the at-least-once
ClickHouse dedup absorbs them — webhook idempotence for free, by design.
Amounts are signed (churn is negative) so `sum(value)` reads as MRR
movement over a period.
"""

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_NAMESPACE = uuid.UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")  # uuid5 OID ns

_STRIPE_EVENTS: dict[str, str] = {
    "customer.subscription.created": "revenue_subscription_created",
    "customer.subscription.updated": "revenue_subscription_updated",
    "customer.subscription.deleted": "revenue_churn",
    "customer.subscription.trial_will_end": "revenue_trial_ending",
}
_LS_EVENTS: dict[str, str] = {
    "subscription_created": "revenue_subscription_created",
    "subscription_updated": "revenue_subscription_updated",
    "subscription_cancelled": "revenue_churn",
    "order_created": "revenue_order",
}
_NEGATIVE = {"revenue_churn"}


@dataclass(frozen=True)
class RevenueEvent:
    event_id: uuid.UUID
    name: str
    amount: float  # currency units, signed (churn < 0)
    props: dict[str, Any] = field(default_factory=dict)


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, *, tolerance_s: int = 300
) -> bool:
    parts = dict(
        item.split("=", 1) for item in header.split(",") if "=" in item
    )
    timestamp, signature = parts.get("t"), parts.get("v1")
    if not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > tolerance_s:
            return False
    except ValueError:
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_lemonsqueezy_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _revenue(provider: str, provider_event_id: str, name: str, amount: float,
             currency: str, plan: str) -> RevenueEvent:
    signed = -abs(amount) if name in _NEGATIVE else amount
    return RevenueEvent(
        event_id=uuid.uuid5(_NAMESPACE, f"{provider}:{provider_event_id}"),
        name=name,
        amount=round(signed, 2),
        props={"provider": provider, "currency": currency, "plan": plan},
    )


def map_stripe_event(payload: dict[str, Any]) -> RevenueEvent | None:
    name = _STRIPE_EVENTS.get(str(payload.get("type", "")))
    if name is None:
        return None
    obj = (payload.get("data") or {}).get("object") or {}
    plan = obj.get("plan") or {}
    amount = float(plan.get("amount") or 0) / 100  # Stripe amounts are cents
    return _revenue(
        "stripe", str(payload.get("id", "")), name, amount,
        str(plan.get("currency", "")), str(plan.get("nickname") or ""),
    )


def map_lemonsqueezy_event(payload: dict[str, Any]) -> RevenueEvent | None:
    meta = payload.get("meta") or {}
    name = _LS_EVENTS.get(str(meta.get("event_name", "")))
    if name is None:
        return None
    attributes = (payload.get("data") or {}).get("attributes") or {}
    amount = float(attributes.get("total") or 0) / 100  # LS totals are cents
    return _revenue(
        "lemonsqueezy",
        str(meta.get("webhook_id", "")),
        name,
        amount,
        str(attributes.get("currency", "")),
        str(attributes.get("variant_name") or ""),
    )
