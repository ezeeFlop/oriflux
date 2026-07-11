"""Seam: monthly event quota enforcement at ingest (issue #60, PRD #59).

The quota is data (plans table), the counter is Redis, the gate is the
ingest HTTP surface: within quota → 202 with X-Oriflux-Quota-* headers;
beyond quota × (1 + tolerance) → 429 with the same headers. Orgs on an
unlimited plan (monthly_events NULL) and orgs whose plan row is missing
are never blocked (fail-open — losing events over a config mistake would
violate the SDK-safety constraint harder than overserving does).
"""

import uuid
from datetime import UTC, datetime

import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import ApiKey, KeyScope, Organization, Plan, Project, Source, SourceType
from oriflux.quota import QuotaExceeded, QuotaMeter
from oriflux.security.keys import generate_api_key
from tests.unit.test_ingest_auth import auth, make_client

VALID_EVENT = {"type": "pageview", "url": "https://audigeo.ai/"}


async def seed_with_plan(
    factory: async_sessionmaker[AsyncSession],
    *,
    monthly_events: int | None,
    plan_slug: str = "test-plan",
    create_plan_row: bool = True,
) -> str:
    """org on a plan with the given quota; returns a valid ingest key."""
    async with factory() as session:
        if create_plan_row:
            session.add(Plan(slug=plan_slug, name="Test", monthly_events=monthly_events))
        org = Organization(slug=f"org-{uuid.uuid4().hex[:8]}", name="Org", plan_slug=plan_slug)
        session.add(org)
        await session.flush()
        project = Project(org_id=org.id, slug=f"p-{uuid.uuid4().hex[:6]}", name="P")
        session.add(project)
        await session.flush()
        source = Source(project_id=project.id, type=SourceType.web, name="site")
        session.add(source)
        await session.flush()
        key = generate_api_key(KeyScope.ingest)
        session.add(
            ApiKey(
                org_id=org.id, source_id=source.id, scope=KeyScope.ingest,
                key_hash=key.key_hash, key_prefix=key.key_prefix,
            )
        )
        await session.commit()
        return key.plaintext


class TestIngestQuotaGate:
    async def test_within_quota_is_202_with_headers(
        self, redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        key = await seed_with_plan(db_sessionmaker, monthly_events=10)
        async with make_client(redis, db_sessionmaker, ingest_quota_tolerance_pct=0) as client:
            response = await client.post("/api/v1/events", json=VALID_EVENT, headers=auth(key))
            assert response.status_code == 202, response.text
            assert response.headers["x-oriflux-quota-limit"] == "10"
            assert response.headers["x-oriflux-quota-used"] == "1"
            assert response.headers["x-oriflux-quota-remaining"] == "9"

    async def test_beyond_quota_and_tolerance_is_429(
        self, redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        key = await seed_with_plan(db_sessionmaker, monthly_events=2)
        async with make_client(
            redis, db_sessionmaker, ingest_quota_tolerance_pct=50
        ) as client:
            for _ in range(3):  # 2 × 1.5 tolerance → the 3rd still passes
                ok = await client.post("/api/v1/events", json=VALID_EVENT, headers=auth(key))
                assert ok.status_code == 202, ok.text
            rejected = await client.post(
                "/api/v1/events", json=VALID_EVENT, headers=auth(key)
            )
            assert rejected.status_code == 429
            assert rejected.headers["x-oriflux-quota-limit"] == "2"
            assert "quota" in rejected.json()["detail"]

    async def test_unlimited_plan_is_never_blocked(
        self, redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        key = await seed_with_plan(db_sessionmaker, monthly_events=None)
        async with make_client(redis, db_sessionmaker) as client:
            for _ in range(5):
                response = await client.post(
                    "/api/v1/events", json=VALID_EVENT, headers=auth(key)
                )
                assert response.status_code == 202
            assert "x-oriflux-quota-limit" not in response.headers

    async def test_missing_plan_row_fails_open(
        self, redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        key = await seed_with_plan(
            db_sessionmaker, monthly_events=1, plan_slug="ghost", create_plan_row=False
        )
        async with make_client(redis, db_sessionmaker, ingest_quota_tolerance_pct=0) as client:
            for _ in range(3):
                response = await client.post(
                    "/api/v1/events", json=VALID_EVENT, headers=auth(key)
                )
                assert response.status_code == 202

    async def test_api_metrics_count_by_entries(
        self, redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        key = await seed_with_plan(db_sessionmaker, monthly_events=3)
        payload = {
            "window_start": "2026-07-11T10:00:00Z",
            "entries": [
                {"endpoint": "/a", "method": "GET", "status_code": 200, "count": 5},
                {"endpoint": "/b", "method": "GET", "status_code": 200, "count": 2},
            ],
        }
        async with make_client(redis, db_sessionmaker, ingest_quota_tolerance_pct=0) as client:
            first = await client.post("/api/v1/api-metrics", json=payload, headers=auth(key))
            assert first.status_code == 202, first.text
            assert first.headers["x-oriflux-quota-used"] == "2"
            second = await client.post("/api/v1/api-metrics", json=payload, headers=auth(key))
            assert second.status_code == 429


class TestQuotaMeter:
    async def test_counter_resets_with_the_month(
        self, redis: FakeAsyncRedis, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        async with db_sessionmaker() as session:
            session.add(Plan(slug="tiny", name="Tiny", monthly_events=1))
            org = Organization(slug="reset-org", name="R", plan_slug="tiny")
            session.add(org)
            await session.commit()
            org_id = str(org.id)

        meter = QuotaMeter(redis, db_sessionmaker, tolerance_pct=0, limit_cache_ttl_s=0)
        july = datetime(2026, 7, 11, tzinfo=UTC)
        august = datetime(2026, 8, 1, tzinfo=UTC)
        await meter.count(org_id, 1, now=july)
        with pytest.raises(QuotaExceeded):
            await meter.count(org_id, 1, now=july)
        status = await meter.count(org_id, 1, now=august)  # new month, fresh counter
        assert status.used == 1


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()
