"""Ingest key resolution: plaintext key → (key id, org, project), cached.

PostgreSQL is looked up at most once per key per TTL (default 30 s) so the
hot ingest path stays off the database; revocation therefore takes effect
within one TTL. Negative results are cached too (unknown-key floods must
not hammer PostgreSQL).
"""

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.db.models import ApiKey, KeyScope, Project, Source
from oriflux.security.keys import hash_api_key


class UnknownKey(Exception):
    """Missing, unknown, or revoked — indistinguishable to the caller (401)."""


class WrongScope(Exception):
    """The key exists but is not ingest-scoped (403)."""


@dataclass(frozen=True)
class ResolvedIngestKey:
    key_id: str
    org_id: str
    project_id: str
    source_id: str


class IngestKeyResolver:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, cache_ttl_s: float
    ) -> None:
        self._session_factory = session_factory
        self._cache_ttl_s = cache_ttl_s
        # key_hash → (expires_at, resolved | exception to re-raise)
        self._cache: dict[str, tuple[float, ResolvedIngestKey | Exception]] = {}

    async def resolve(self, plaintext: str) -> ResolvedIngestKey:
        key_hash = hash_api_key(plaintext)
        cached = self._cache.get(key_hash)
        if cached is not None and cached[0] > time.monotonic():
            if isinstance(cached[1], Exception):
                raise cached[1]
            return cached[1]

        try:
            resolved = await self._lookup(key_hash)
        except (UnknownKey, WrongScope) as exc:
            self._remember(key_hash, exc)
            raise
        self._remember(key_hash, resolved)
        return resolved

    _MAX_ENTRIES = 10_000

    def _remember(self, key_hash: str, value: ResolvedIngestKey | Exception) -> None:
        self._cache[key_hash] = (time.monotonic() + self._cache_ttl_s, value)
        if len(self._cache) > self._MAX_ENTRIES:
            self._evict()

    def _evict(self) -> None:
        """Bound memory under a random-key flood WITHOUT dropping live
        positive entries wholesale: expired entries first, then oldest-
        inserted (dicts preserve insertion order) down to half capacity."""
        now = time.monotonic()
        for key in [k for k, (expires, _) in self._cache.items() if expires <= now]:
            del self._cache[key]
        while len(self._cache) > self._MAX_ENTRIES // 2:
            del self._cache[next(iter(self._cache))]

    async def _lookup(self, key_hash: str) -> ResolvedIngestKey:
        async with self._session_factory() as session:
            key = (
                await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
            ).scalar_one_or_none()
            if key is None or key.revoked_at is not None:
                raise UnknownKey()
            if key.scope != KeyScope.ingest or key.source_id is None:
                raise WrongScope()
            source = await session.get(Source, key.source_id)
            assert source is not None  # FK guarantees it
            project = await session.get(Project, source.project_id)
            assert project is not None
            return ResolvedIngestKey(
                key_id=str(key.id),
                org_id=str(project.org_id),
                project_id=str(project.id),
                source_id=str(source.id),
            )
