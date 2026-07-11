"""Monthly event quota per organization (issue #60, PRD #59).

The limit is data (plans table, looked up through a short in-process cache
so the hot ingest path stays off PostgreSQL), the counter is a per-month
Redis key shared by every ingest replica, the tolerance is configuration.
Fail-open by design: an unlimited plan (monthly_events NULL) or a missing
plan row never blocks ingestion — dropping a customer's events over a
config mistake would break the product promise harder than overserving.

The Redis counter also counts rejected attempts once past the line; it is
a gate, not a billing meter — ClickHouse remains the authoritative count.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import Organization, Plan

_COUNTER_TTL_S = 40 * 86400  # outlives the month, then expires on its own


@dataclass
class QuotaStatus:
    limit: int | None  # None = unlimited
    used: int

    @property
    def remaining(self) -> int | None:
        if self.limit is None:
            return None
        return max(0, self.limit - self.used)

    def headers(self) -> dict[str, str]:
        if self.limit is None:
            return {}
        return {
            "X-Oriflux-Quota-Limit": str(self.limit),
            "X-Oriflux-Quota-Used": str(self.used),
            "X-Oriflux-Quota-Remaining": str(self.remaining),
        }


class QuotaExceeded(Exception):
    def __init__(self, status: QuotaStatus) -> None:
        super().__init__("monthly event quota exceeded")
        self.status = status


class QuotaMeter:
    def __init__(
        self,
        redis: Redis,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        tolerance_pct: int,
        limit_cache_ttl_s: float = 60.0,
    ) -> None:
        self._redis = redis
        self._factory = session_factory
        self._tolerance_pct = tolerance_pct
        self._cache_ttl_s = limit_cache_ttl_s
        self._limits: dict[str, tuple[float, int | None]] = {}

    async def _limit_for(self, org_id: str) -> int | None:
        cached = self._limits.get(org_id)
        if cached is not None and (time.monotonic() - cached[0]) <= self._cache_ttl_s:
            return cached[1]
        async with self._factory() as session:
            row = (
                await session.execute(
                    select(Plan.monthly_events)
                    .join(Organization, Organization.plan_slug == Plan.slug)
                    .where(Organization.id == uuid.UUID(org_id))
                )
            ).scalar_one_or_none()
        self._limits[org_id] = (time.monotonic(), row)
        return row

    async def count(self, org_id: str, n: int, *, now: datetime) -> QuotaStatus:
        """Add n events to the org's monthly counter; raise beyond
        limit × (1 + tolerance)."""
        limit = await self._limit_for(org_id)
        counter_key = f"oriflux:quota:{org_id}:{now:%Y%m}"
        used = int(await self._redis.incrby(counter_key, n))
        if used == n:
            await self._redis.expire(counter_key, _COUNTER_TTL_S)
        status = QuotaStatus(limit=limit, used=used)
        if limit is not None and used > limit * (1 + self._tolerance_pct / 100):
            raise QuotaExceeded(status)
        return status
