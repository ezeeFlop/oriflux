"""Daily-rotating visitor hash (PRD §9, Plausible pattern).

unique visitor = sha256(daily_salt | project_id | ip | user_agent)

The salt lives only in Redis: created on first use of day D (SET NX),
destroyed by TTL — 26 h from first use, so it covers the rest of D (plus
clock skew) and is gone early into D+1. No salt, no way to link a visitor
across days or across projects; that is the property the no-consent-banner
positioning rests on. Never reintroduce a persistent anonymous ID.
"""

import hashlib
import secrets
from datetime import date

from redis.asyncio import Redis

_SALT_TTL_S = 26 * 3600


class VisitorHasher:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        # per-process memo so the hot path doesn't hit Redis per event;
        # pruned to the current day so no salt outlives its Redis TTL here
        self._salts: dict[str, str] = {}

    async def _daily_salt(self, day: date) -> str:
        iso = day.isoformat()
        cached = self._salts.get(iso)
        if cached is not None:
            return cached
        key = f"oriflux:visitor_salt:{iso}"
        await self._redis.set(key, secrets.token_hex(32), nx=True, ex=_SALT_TTL_S)
        raw = await self._redis.get(key)
        if raw is None:
            # expiry race (SET NX landed just before the TTL wiped it) —
            # never fall back to a constant: that would be a de-facto
            # persistent ID. Recreate and re-read.
            await self._redis.set(key, secrets.token_hex(32), nx=True, ex=_SALT_TTL_S)
            raw = await self._redis.get(key)
        if raw is None:
            raise RuntimeError("could not obtain a daily visitor salt from Redis")
        salt = raw.decode() if isinstance(raw, bytes) else str(raw)
        self._salts = {iso: salt}  # exactly one day memoized
        return salt

    async def visitor_hash(self, project_id: str, ip: str, user_agent: str, *, day: date) -> str:
        salt = await self._daily_salt(day)
        material = f"{salt}|{project_id}|{ip}|{user_agent}"
        return hashlib.sha256(material.encode()).hexdigest()
