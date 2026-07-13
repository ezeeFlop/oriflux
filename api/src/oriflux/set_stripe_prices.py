"""Attach Stripe price IDs to the subscribable plans (#65).

Prices are data, not code (plans.stripe_price_id) — no amount is ever
hardcoded. This command reads the price IDs from the environment and writes
them onto the matching plan rows, so activating billing never means editing
SQL by hand. Idempotent: re-running with the same values is a no-op.

    # in the Portainer stack env (price IDs are not secrets):
    #   ORIFLUX_STRIPE_PRICE_PRO=price_...
    #   ORIFLUX_STRIPE_PRICE_SCALE=price_...
    docker compose exec api python -m oriflux.set_stripe_prices

Price IDs come from the Stripe dashboard (Products → your price → API ID).
The Stripe SECRET key is NEVER handled here — only the public price IDs.
"""

import asyncio
import os
import sys

from sqlalchemy import text

from oriflux.config import get_settings
from oriflux.db import create_engine, create_session_factory

# plan slug → env var carrying its Stripe price ID (free has no price)
_PLAN_PRICE_ENV = {
    "pro": "ORIFLUX_STRIPE_PRICE_PRO",
    "scale": "ORIFLUX_STRIPE_PRICE_SCALE",
}


async def apply_prices() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    applied, skipped = [], []
    async with factory() as session:
        for slug, env_var in _PLAN_PRICE_ENV.items():
            price_id = os.environ.get(env_var, "").strip()
            if not price_id:
                skipped.append(f"{slug} ({env_var} unset)")
                continue
            result = await session.execute(
                text("UPDATE plans SET stripe_price_id = :pid WHERE slug = :slug"),
                {"pid": price_id, "slug": slug},
            )
            if result.rowcount:  # type: ignore[attr-defined]  # CursorResult exposes it
                applied.append(f"{slug} → {price_id}")
            else:
                skipped.append(f"{slug} (no such plan row)")
        await session.commit()
    await engine.dispose()

    for line in applied:
        print(f"set {line}")
    for line in skipped:
        print(f"skip {line}")
    if not applied:
        print("no price IDs applied — set ORIFLUX_STRIPE_PRICE_PRO / _SCALE first")


if __name__ == "__main__":
    sys.exit(asyncio.run(apply_prices()))
