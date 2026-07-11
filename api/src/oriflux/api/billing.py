"""Billing REST (issue #63): thin Stripe endpoints + the idempotent webhook.

Prices are data (plans.stripe_price_id); the webhook is the single writer
of plan changes; a replayed event is a no-op through the stripe_events
ledger. With billing disabled (no secret key) the read endpoint says so
and everything else in the product keeps working on free/internal plans.
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.billing import BillingGateway, CheckoutRequest, InvalidSignature
from oriflux.db.models import Organization, Plan, Role, StripeEvent, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["billing"])


class BillingPlanOut(BaseModel):
    slug: str
    name: str
    monthly_events: int | None
    subscribable: bool  # has a Stripe price


class BillingOut(BaseModel):
    enabled: bool
    plan_slug: str
    has_customer: bool
    plans: list[BillingPlanOut]


class CheckoutIn(BaseModel):
    plan_slug: str


class HostedUrlOut(BaseModel):
    url: str


def _gateway(request: Request) -> BillingGateway:
    gateway: BillingGateway = request.app.state.billing
    return gateway


@router.get("/orgs/{org_id}/billing")
async def billing_state(
    org_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BillingOut:
    await require_role(session, user, org_id, Role.viewer)
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org not found")
    plans = (
        (await session.execute(select(Plan).order_by(Plan.slug))).scalars().all()
    )
    return BillingOut(
        enabled=_gateway(request).enabled,
        plan_slug=org.plan_slug,
        has_customer=org.stripe_customer_id is not None,
        plans=[
            BillingPlanOut(
                slug=p.slug,
                name=p.name,
                monthly_events=p.monthly_events,
                subscribable=p.stripe_price_id is not None,
            )
            for p in plans
        ],
    )


@router.post("/orgs/{org_id}/billing/checkout")
async def create_checkout(
    org_id: uuid.UUID,
    payload: CheckoutIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HostedUrlOut:
    await require_role(session, user, org_id, Role.admin)
    gateway = _gateway(request)
    if not gateway.enabled:
        raise HTTPException(status_code=503, detail="billing is not configured")
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org not found")
    plan = await session.get(Plan, payload.plan_slug)
    if plan is None or plan.stripe_price_id is None:
        raise HTTPException(status_code=422, detail="plan is not subscribable")
    base = request.app.state.settings.web_base_url
    url = gateway.create_checkout(
        CheckoutRequest(
            org_id=str(org_id),
            customer_id=org.stripe_customer_id,
            customer_email=user.email,
            price_id=plan.stripe_price_id,
            plan_slug=plan.slug,
            success_url=f"{base}/settings/org?billing=success",
            cancel_url=f"{base}/settings/org?billing=cancelled",
        )
    )
    return HostedUrlOut(url=url)


@router.post("/orgs/{org_id}/billing/portal")
async def create_portal(
    org_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HostedUrlOut:
    await require_role(session, user, org_id, Role.admin)
    gateway = _gateway(request)
    if not gateway.enabled:
        raise HTTPException(status_code=503, detail="billing is not configured")
    org = await session.get(Organization, org_id)
    if org is None or org.stripe_customer_id is None:
        raise HTTPException(status_code=409, detail="no billing customer yet")
    base = request.app.state.settings.web_base_url
    return HostedUrlOut(
        url=gateway.create_portal(org.stripe_customer_id, f"{base}/settings/org")
    )


async def _org_for_event(
    session: AsyncSession, data: dict[str, Any]
) -> Organization | None:
    """An event names its org via metadata (set at checkout) or via the
    stored customer id."""
    org_id = (data.get("metadata") or {}).get("org_id") or data.get("client_reference_id")
    if org_id:
        try:
            return await session.get(Organization, uuid.UUID(str(org_id)))
        except ValueError:
            return None
    customer = data.get("customer")
    if customer:
        return (
            await session.execute(
                select(Organization).where(Organization.stripe_customer_id == str(customer))
            )
        ).scalar_one_or_none()
    return None


async def _plan_for_price(session: AsyncSession, price_id: str | None) -> Plan | None:
    if price_id is None:
        return None
    return (
        await session.execute(select(Plan).where(Plan.stripe_price_id == price_id))
    ).scalar_one_or_none()


@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    gateway = _gateway(request)
    if not gateway.enabled:
        raise HTTPException(status_code=503, detail="billing is not configured")
    payload = await request.body()
    try:
        event = gateway.parse_webhook(payload, request.headers.get("stripe-signature", ""))
    except InvalidSignature as exc:
        raise HTTPException(status_code=400, detail="invalid signature") from exc

    event_id = str(event.get("id", ""))
    if event_id == "":
        raise HTTPException(status_code=400, detail="event without id")
    session.add(StripeEvent(id=event_id))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return {"received": True, "duplicate": True}

    kind = str(event.get("type", ""))
    data: dict[str, Any] = (event.get("data") or {}).get("object") or {}
    org = await _org_for_event(session, data)

    if org is not None:
        if kind == "checkout.session.completed":
            plan_slug = (data.get("metadata") or {}).get("plan_slug")
            if plan_slug and await session.get(Plan, str(plan_slug)) is not None:
                org.plan_slug = str(plan_slug)
            if data.get("customer"):
                org.stripe_customer_id = str(data["customer"])
        elif kind == "customer.subscription.updated":
            items = ((data.get("items") or {}).get("data")) or []
            price_id = ((items[0].get("price") or {}).get("id")) if items else None
            plan = await _plan_for_price(session, price_id)
            if plan is not None:
                org.plan_slug = plan.slug
        elif kind == "customer.subscription.deleted":
            org.plan_slug = "free"
    else:
        logger.warning("stripe webhook %s (%s): no matching org", event_id, kind)

    await session.commit()
    return {"received": True, "duplicate": False}
