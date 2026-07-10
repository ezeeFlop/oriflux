"""Ingestion rate limiting per key and per IP (PRD §9).

Fixed one-minute windows in Redis (INCR + EXPIRE): distributed-safe across
ingest replicas, one round-trip per dimension, ~2× burst at window edges —
fine for abuse protection (this is not billing metering).
"""

import hashlib
import time

from redis.asyncio import Redis


class RateLimited(Exception):
    def __init__(self, dimension: str) -> None:
        super().__init__(f"rate limit exceeded ({dimension})")
        self.dimension = dimension


class RateLimiter:
    def __init__(self, redis: Redis, *, per_key: int, per_ip: int) -> None:
        self._redis = redis
        self._per_key = per_key
        self._per_ip = per_ip

    async def _count(self, bucket: str) -> int:
        window = int(time.time()) // 60
        redis_key = f"oriflux:rl:{bucket}:{window}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, 120)
        return int(count)

    async def check_ip(self, ip: str) -> None:
        """Runs before authentication — meters every request, valid key or not.
        The bucket key hashes the IP so the raw address never sits in Redis
        (PRD §9: IP resolved at ingestion then discarded)."""
        digest = hashlib.sha256(ip.encode()).hexdigest()[:16]
        if await self._count(f"ip:{digest}") > self._per_ip:
            raise RateLimited("ip")

    async def check_key(self, key_id: str) -> None:
        if await self._count(f"key:{key_id}") > self._per_key:
            raise RateLimited("key")
