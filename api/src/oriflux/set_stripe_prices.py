"""Attach Stripe price IDs + cached amounts to the subscribable plans (#65).

Prices are data, not code (plans.stripe_price_id) — no amount is ever
hardcoded. The price IDs come from the environment and are written onto the
matching plan rows, with the live amount read back from Stripe. Idempotent.

This runs automatically at api startup (so "set the env, redeploy" is all it
takes), and is also a standalone command for an on-demand re-sync:

    # in the Portainer stack env (price IDs are not secrets):
    #   ORIFLUX_STRIPE_PRICE_PRO=price_...          # monthly
    #   ORIFLUX_STRIPE_PRICE_SCALE=price_...
    #   ORIFLUX_STRIPE_PRICE_PRO_ANNUAL=price_...   # optional (2 months free)
    #   ORIFLUX_STRIPE_PRICE_SCALE_ANNUAL=price_...
    docker compose exec api python -m oriflux.set_stripe_prices

Price IDs come from the Stripe dashboard (Products → your price → API ID).
The Stripe SECRET key is NEVER handled here — only the public price IDs.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.billing import BillingGateway, StripeGateway
from oriflux.config import get_settings
from oriflux.db import create_engine, create_session_factory

# plan slug → (monthly env var, annual env var). Free has no price; annual
# is optional (2 months free) and independent of the monthly cadence.
_PLAN_PRICE_ENV = {
    "pro": ("ORIFLUX_STRIPE_PRICE_PRO", "ORIFLUX_STRIPE_PRICE_PRO_ANNUAL"),
    "scale": ("ORIFLUX_STRIPE_PRICE_SCALE", "ORIFLUX_STRIPE_PRICE_SCALE_ANNUAL"),
}
# which amount column caches which cadence
_AMOUNT_COLUMN = {
    "stripe_price_id": "amount_cents",
    "stripe_price_id_annual": "amount_cents_annual",
}


async def sync_prices(
    factory: async_sessionmaker[AsyncSession], gateway: BillingGateway
) -> tuple[list[str], list[str]]:
    """Write env price IDs + live Stripe amounts onto the plan rows.
    Returns (applied, skipped) human-readable lines. Never raises on an
    individual price it cannot resolve."""
    applied: list[str] = []
    skipped: list[str] = []
    async with factory() as session:
        for slug, (monthly_env, annual_env) in _PLAN_PRICE_ENV.items():
            for id_column, env_var, cadence in (
                ("stripe_price_id", monthly_env, "monthly"),
                ("stripe_price_id_annual", annual_env, "annual"),
            ):
                price_id = os.environ.get(env_var, "").strip()
                if not price_id:
                    skipped.append(f"{slug} {cadence} ({env_var} unset)")
                    continue
                # read the live amount from Stripe (never hardcoded); cache it
                # alongside the id so the public pricing endpoint stays fast
                info = gateway.get_price(price_id) if gateway.enabled else None
                amount_col = _AMOUNT_COLUMN[id_column]
                result = await session.execute(
                    text(
                        f"UPDATE plans SET {id_column} = :pid, {amount_col} = :amt, "
                        "currency = COALESCE(:cur, currency) WHERE slug = :slug"
                    ),
                    {
                        "pid": price_id,
                        "amt": info.amount_cents if info else None,
                        "cur": info.currency if info else None,
                        "slug": slug,
                    },
                )
                if result.rowcount:  # type: ignore[attr-defined]  # CursorResult exposes it
                    money = f" ({info.amount_cents / 100:.2f} {info.currency})" if info else ""
                    applied.append(f"{slug} {cadence} → {price_id}{money}")
                else:
                    skipped.append(f"{slug} {cadence} (no such plan row)")
        await session.commit()
    return applied, skipped


async def apply_prices() -> None:
    settings = get_settings()
    gateway = StripeGateway(settings.stripe_secret_key, settings.stripe_webhook_secret)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    applied, skipped = await sync_prices(factory, gateway)
    await engine.dispose()

    for line in applied:
        print(f"set {line}")
    for line in skipped:
        print(f"skip {line}")
    if not applied:
        print("no price IDs applied — set ORIFLUX_STRIPE_PRICE_PRO / _SCALE first")


if __name__ == "__main__":
    sys.exit(asyncio.run(apply_prices()))
