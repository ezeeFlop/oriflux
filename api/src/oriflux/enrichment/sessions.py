"""Cookieless sessionization (issue #6): visitor hash → session id in Redis.

A session ends after 30 minutes of inactivity (industry convention). The
mapping key is the daily-rotating pseudonymous visitor hash and lives at
most SESSION_GAP_S — nothing here survives the day or identifies a person.
SET NX + read-back keeps concurrent first events of a visitor on one id.
"""

import uuid

from redis.asyncio import Redis

SESSION_GAP_S = 30 * 60


class SessionTracker:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def session_for(self, visitor_hash: str) -> str:
        key = f"oriflux:session:{visitor_hash}"
        await self._redis.set(key, uuid.uuid4().hex, nx=True, ex=SESSION_GAP_S)
        raw = await self._redis.get(key)
        if raw is None:  # expiry race: recreate
            await self._redis.set(key, uuid.uuid4().hex, nx=True, ex=SESSION_GAP_S)
            raw = await self._redis.get(key)
        if raw is None:
            raise RuntimeError("could not obtain a session id from Redis")
        # every event slides the inactivity window
        await self._redis.expire(key, SESSION_GAP_S)
        return raw.decode() if isinstance(raw, bytes) else str(raw)
