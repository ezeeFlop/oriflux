"""Seam: the digest send job (issue #26) — idempotent, injectable sender."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import DigestSubscription, Organization, Project, User
from oriflux.workers.digest_job import run_digests

MONDAY = datetime(2026, 7, 6, 0, 30, tzinfo=UTC)
TUESDAY = datetime(2026, 7, 7, 0, 30, tzinfo=UTC)


class FlatExecutor:
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"value": 42}]


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def __call__(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


async def seed_subscription(
    sessionmaker: async_sessionmaker[AsyncSession], *, cadence: str = "weekly"
) -> None:
    async with sessionmaker() as session:
        org = Organization(slug="spt", name="SPT")
        user = User(email="christophe@sponge-theory.io", google_sub="g-1")
        session.add_all([org, user])
        await session.flush()
        session.add(Project(org_id=org.id, slug="audigeo", name="AudiGEO"))
        session.add(
            DigestSubscription(org_id=org.id, user_id=user.id, cadence=cadence, language="fr")
        )
        await session.commit()


class TestRunDigests:
    async def test_weekly_digest_goes_out_on_monday_in_the_right_language(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed_subscription(db_sessionmaker)
        sender = RecordingSender()
        sent = await run_digests(db_sessionmaker, FlatExecutor(), sender, now=MONDAY)
        assert sent == 1
        to, subject, body = sender.sent[0]
        assert to == "christophe@sponge-theory.io"
        assert "digest" in subject.lower()
        assert "Visiteurs" in body  # fr
        assert "AudiGEO" in body

    async def test_sending_is_idempotent_per_period(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed_subscription(db_sessionmaker)
        sender = RecordingSender()
        await run_digests(db_sessionmaker, FlatExecutor(), sender, now=MONDAY)
        again = await run_digests(db_sessionmaker, FlatExecutor(), sender, now=MONDAY)
        assert again == 0
        assert len(sender.sent) == 1

    async def test_nothing_goes_out_off_schedule(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed_subscription(db_sessionmaker)
        sender = RecordingSender()
        assert await run_digests(db_sessionmaker, FlatExecutor(), sender, now=TUESDAY) == 0


class TestDigestPrefApi:
    async def test_member_sets_reads_and_unsubscribes(self, api_client) -> None:  # type: ignore[no-untyped-def]
        from tests.unit.conftest import login
        from tests.unit.test_auth_and_admin import create_org_chain

        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)

        put = await api_client.put(
            f"/api/v1/orgs/{org_id}/digest",
            json={"cadence": "weekly", "language": "fr"},
            headers=owner,
        )
        assert put.status_code == 200, put.text

        got = await api_client.get(f"/api/v1/orgs/{org_id}/digest", headers=owner)
        assert got.json() == {"cadence": "weekly", "language": "fr"}

        gone = await api_client.delete(f"/api/v1/orgs/{org_id}/digest", headers=owner)
        assert gone.status_code == 204
        after = await api_client.get(f"/api/v1/orgs/{org_id}/digest", headers=owner)
        assert after.status_code == 404
