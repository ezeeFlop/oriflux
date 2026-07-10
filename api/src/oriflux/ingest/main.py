"""oriflux_ingest — stateless collection service.

POST /api/v1/events: per-source ingest key (validated against PostgreSQL,
cached) → rate limiting per key and per IP → Pydantic validation → UUID
assignment → Redis Streams buffer. The event's org/project come from the
key's source — multi-tenancy is stamped at the door, never trusted from the
payload. Enrichment (geo, UA, bot classification, visitor hash) plugs into
this path with issue #4.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings, get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.ingest.auth import IngestKeyResolver, ResolvedIngestKey, UnknownKey, WrongScope
from oriflux.models.events import EnrichedEvent, PageviewIn
from oriflux.ratelimit import RateLimited, RateLimiter
from oriflux.storage.redis_stream import publish_event

_bearer = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str:
    # Take the RIGHTMOST X-Forwarded-For element: it is the one appended by
    # our own proxy (Traefik). Leftmost values are attacker-controlled and
    # would let callers rotate around the per-IP limit.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def create_app(
    redis: Redis | None = None,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.redis = redis or Redis.from_url(settings.redis_url)
        engine = None
        if session_factory is None:
            engine = create_engine(settings)
            factory = create_session_factory(engine)
        else:
            factory = session_factory
        app.state.resolver = IngestKeyResolver(
            factory, cache_ttl_s=settings.api_key_cache_ttl_s
        )
        app.state.rate_limiter = RateLimiter(
            app.state.redis,
            per_key=settings.ingest_rate_limit_per_key,
            per_ip=settings.ingest_rate_limit_per_ip,
        )
        yield
        await app.state.redis.aclose()
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="oriflux_ingest", lifespan=lifespan)
    # For test transports that skip lifespan, wire the injected boundaries anyway.
    if redis is not None and session_factory is not None:
        app.state.redis = redis
        app.state.resolver = IngestKeyResolver(
            session_factory, cache_ttl_s=settings.api_key_cache_ttl_s
        )
        app.state.rate_limiter = RateLimiter(
            redis,
            per_key=settings.ingest_rate_limit_per_key,
            per_ip=settings.ingest_rate_limit_per_ip,
        )

    async def authenticate(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> ResolvedIngestKey:
        limiter: RateLimiter = request.app.state.rate_limiter
        try:
            # Per-IP limit runs BEFORE key resolution so unauthenticated
            # floods (random keys = guaranteed cache misses) are metered and
            # can never hammer PostgreSQL unchecked.
            await limiter.check_ip(_client_ip(request))
            if credentials is None:
                raise HTTPException(status_code=401, detail="missing API key")
            try:
                resolved: ResolvedIngestKey = await request.app.state.resolver.resolve(
                    credentials.credentials
                )
            except UnknownKey as exc:
                raise HTTPException(
                    status_code=401, detail="invalid or revoked API key"
                ) from exc
            except WrongScope as exc:
                raise HTTPException(status_code=403, detail="key lacks ingest scope") from exc
            await limiter.check_key(resolved.key_id)
        except RateLimited as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        return resolved

    @app.post("/api/v1/events", status_code=202)
    async def collect(
        pageview: PageviewIn,
        request: Request,
        key: ResolvedIngestKey = Depends(authenticate),
    ) -> dict[str, str]:
        event = EnrichedEvent.from_pageview(
            pageview,
            org_id=key.org_id,
            project_id=key.project_id,
            timestamp=datetime.now(tz=UTC),
        )
        await publish_event(request.app.state.redis, event)
        return {"event_id": str(event.event_id)}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
