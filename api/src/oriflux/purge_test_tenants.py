"""Purge the integration-test tenants (#66 quality item).

Integration runs seed throwaway orgs (slugs ``it-a-*`` / ``it-b-*``) straight
into PostgreSQL and their events into ClickHouse; nothing ever deletes them.
This command removes every trace of them — and ONLY them: the slug pattern is
hardcoded, there is no way to point it at a real tenant.

    docker compose exec api python -m oriflux.purge_test_tenants
"""

import asyncio
import sys

from sqlalchemy import text

from oriflux.config import get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.storage.clickhouse import get_client

TEST_SLUG_PATTERN = "it-%"

# children before parents (FK order); every table carrying an org_id column
# (digest_sends hangs off digest_subscriptions and is handled separately;
# stripe_events has no org linkage at all)
_ORG_TABLES = [
    "ai_usage",
    "alert_events",
    "alert_rules",
    "annotations",
    "anomaly_events",
    "api_keys",
    "connectors",
    "digest_subscriptions",
    "export_schedules",
    "goals",
    "insights",
    "memberships",
    "share_tokens",
]


async def purge() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        org_ids = [
            str(row[0])
            for row in await session.execute(
                text("SELECT id FROM organizations WHERE slug LIKE :pat"),
                {"pat": TEST_SLUG_PATTERN},
            )
        ]
        if not org_ids:
            print("no test tenants found — nothing to purge")
            await engine.dispose()
            return
        params = {"ids": org_ids}
        await session.execute(
            text(
                "DELETE FROM digest_sends WHERE subscription_id IN "
                "(SELECT id FROM digest_subscriptions WHERE org_id = ANY(CAST(:ids AS uuid[])))"
            ),
            params,
        )
        for table in _ORG_TABLES:
            await session.execute(
                text(f"DELETE FROM {table} WHERE org_id = ANY(CAST(:ids AS uuid[]))"), params
            )
        await session.execute(
            text(
                "DELETE FROM sources WHERE project_id IN "
                "(SELECT id FROM projects WHERE org_id = ANY(CAST(:ids AS uuid[])))"
            ),
            params,
        )
        await session.execute(
            text("DELETE FROM projects WHERE org_id = ANY(CAST(:ids AS uuid[]))"), params
        )
        await session.execute(
            text("DELETE FROM organizations WHERE id = ANY(CAST(:ids AS uuid[]))"), params
        )
        await session.commit()
    await engine.dispose()

    client = get_client(settings)
    for table in ("events", "api_minutely"):
        client.command(
            f"ALTER TABLE {table} DELETE WHERE org_id IN %(ids)s",
            parameters={"ids": org_ids},
        )
    print(f"purged {len(org_ids)} test orgs (PostgreSQL + ClickHouse mutations submitted)")


if __name__ == "__main__":
    sys.exit(asyncio.run(purge()))
