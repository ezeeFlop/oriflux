"""Seam: the hourly anomaly-detection job (issue #27)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import AnomalyEvent, Organization, Project
from oriflux.workers.anomaly_job import run_detection

NOW = datetime(2026, 7, 8, 15, 30, tzinfo=UTC)  # Wednesday 15:30 → scores 14:00-15:00


class SeriesExecutor:
    """Returns a seasonal hourly series with a collapse in the last hour."""

    def __init__(self, collapse: bool) -> None:
        self.collapse = collapse

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        start = NOW - timedelta(days=28)
        hour = start.replace(minute=0, second=0, microsecond=0)
        while hour < NOW:
            value = 100.0 if hour.weekday() < 5 else 20.0
            if self.collapse and hour == NOW.replace(minute=0) - timedelta(hours=1):
                value = 10.0
            rows.append({"bucket": hour.isoformat(), "value": value})
            hour += timedelta(hours=1)
        return rows


async def seed_project(
    sessionmaker: async_sessionmaker[AsyncSession], *, muted: bool = False
) -> Project:
    async with sessionmaker() as session:
        org = Organization(slug="spt", name="SPT", anomalies_muted=muted)
        session.add(org)
        await session.flush()
        project = Project(org_id=org.id, slug="audigeo", name="AudiGEO")
        session.add(project)
        await session.commit()
        return project


class TestRunDetection:
    async def test_a_collapse_creates_an_anomaly_event(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        project = await seed_project(db_sessionmaker)
        detections = await run_detection(
            db_sessionmaker, SeriesExecutor(collapse=True), now=NOW
        )
        assert detections >= 1
        async with db_sessionmaker() as session:
            events = (await session.execute(select(AnomalyEvent))).scalars().all()
        assert any(e.project_id == project.id and e.direction == "drop" for e in events)

    async def test_detection_is_idempotent_per_hour(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed_project(db_sessionmaker)
        await run_detection(db_sessionmaker, SeriesExecutor(collapse=True), now=NOW)
        again = await run_detection(db_sessionmaker, SeriesExecutor(collapse=True), now=NOW)
        assert again == 0  # same hour, same anomaly: no duplicate row

    async def test_normal_traffic_creates_nothing(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed_project(db_sessionmaker)
        assert await run_detection(db_sessionmaker, SeriesExecutor(collapse=False), now=NOW) == 0

    async def test_muted_org_is_skipped(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        await seed_project(db_sessionmaker, muted=True)
        assert await run_detection(db_sessionmaker, SeriesExecutor(collapse=True), now=NOW) == 0
