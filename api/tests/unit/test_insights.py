"""Seam: the daily insights feed (issue #35, PRD §6).

Detection is pure statistics; SPT Models only WRITES the insight text
from numbers already computed — and every insight stores its numbers
and the query object that produced them (auditability).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import Insight, Organization, Project
from oriflux.workers.insight_job import run_insights
from oriflux.workers.insights import detect_findings

NOW = datetime(2026, 7, 11, 6, 0, tzinfo=UTC)


class TestDetection:
    def test_material_wow_movement_is_a_finding(self) -> None:
        findings = detect_findings(
            {"visitors": (150.0, 100.0), "pageviews": (400.0, 390.0)}
        )
        assert len(findings) == 1
        [finding] = findings
        assert finding.metric == "visitors"
        assert finding.delta_pct == 50.0
        assert finding.key == "trend:visitors"

    def test_small_movements_and_tiny_volumes_stay_quiet(self) -> None:
        assert detect_findings({"visitors": (105.0, 100.0)}) == []  # +5%: noise
        assert detect_findings({"visitors": (9.0, 3.0)}) == []  # 3x but tiny

    def test_zero_previous_with_real_current_is_a_new_signal(self) -> None:
        [finding] = detect_findings({"api_requests": (500.0, 0.0)})
        assert finding.kind == "new"


class SeriesExecutor:
    """visitors doubled week-over-week; everything else flat."""

    def execute(self, sql, params):  # type: ignore[no-untyped-def]
        if "uniq(visitor_hash)" in sql:
            current_window = params["start"] >= datetime(2026, 7, 4, tzinfo=UTC)
            return [{"value": 300 if current_window else 150}]
        return [{"value": 100}]


class FakeGateway:
    enabled = True

    async def chat(self, org_id, *, feature, messages, temperature=0.2):  # type: ignore[no-untyped-def]
        return "Les visiteurs ont doublé (300 vs 150)."


async def seed(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        org = Organization(slug="spt", name="SPT")
        session.add(org)
        await session.flush()
        session.add(Project(org_id=org.id, slug="audigeo", name="AudiGEO"))
        await session.commit()


class TestRunInsights:
    async def test_findings_become_persisted_insights_with_numbers(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed(db_sessionmaker)
        created = await run_insights(
            db_sessionmaker, SeriesExecutor(), FakeGateway(), now=NOW
        )
        assert created >= 1
        async with db_sessionmaker() as session:
            insights = (await session.execute(select(Insight))).scalars().all()
        visitors = [i for i in insights if i.metric == "visitors"]
        assert visitors, "the doubled visitors trend must be captured"
        assert visitors[0].text.startswith("Les visiteurs")
        assert visitors[0].numbers["current"] == 300

    async def test_idempotent_per_day(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed(db_sessionmaker)
        await run_insights(db_sessionmaker, SeriesExecutor(), FakeGateway(), now=NOW)
        again = await run_insights(db_sessionmaker, SeriesExecutor(), FakeGateway(), now=NOW)
        assert again == 0

    async def test_ai_failure_still_stores_the_numbers(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        class BrokenGateway:
            enabled = True

            async def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("model down")

        await seed(db_sessionmaker)
        created = await run_insights(
            db_sessionmaker, SeriesExecutor(), BrokenGateway(), now=NOW
        )
        assert created >= 1
        async with db_sessionmaker() as session:
            [insight] = [
                i for i in (await session.execute(select(Insight))).scalars()
                if i.metric == "visitors"
            ]
        assert insight.text == ""  # numbers first; prose is optional
