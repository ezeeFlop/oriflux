"""oriflux_ingest — stateless collection service.

POST /api/v1/events: per-source ingest key (validated against PostgreSQL,
cached) → rate limiting per key and per IP → Pydantic validation → UUID
assignment → Redis Streams buffer. The event's org/project come from the
key's source — multi-tenancy is stamped at the door, never trusted from the
payload. Enrichment (geo, UA, bot classification, visitor hash) plugs into
this path with issue #4.
"""

import ipaddress
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.resources import files
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings, get_settings
from oriflux.connectors.revenue import (
    map_lemonsqueezy_event,
    map_stripe_event,
    verify_lemonsqueezy_signature,
    verify_stripe_signature,
)
from oriflux.db import create_engine, create_session_factory
from oriflux.db.models import Connector, ConnectorProvider
from oriflux.enrichment.crawlers import classify_traffic, refine_traffic
from oriflux.enrichment.geo import GeoResolver
from oriflux.enrichment.sessions import SessionTracker
from oriflux.enrichment.ua import parse_ua
from oriflux.enrichment.visitor import VisitorHasher
from oriflux.ingest.auth import IngestKeyResolver, ResolvedIngestKey, UnknownKey, WrongScope
from oriflux.logs import setup_logging
from oriflux.models.api_metrics import ApiMetricsIn, ApiMinuteRow
from oriflux.models.enrichment import GeoInfo
from oriflux.models.events import (
    CustomEventIn,
    EnrichedEvent,
    IdentifyIn,
    PageviewIn,
    VitalIn,
)
from oriflux.ratelimit import RateLimited, RateLimiter
from oriflux.security.secrets import decrypt_secret
from oriflux.storage.redis_stream import publish_api_rows, publish_event

_bearer = HTTPBearer(auto_error=False)

# oriflux.js is bundled with the ingest package and served at a versioned
# path (no npm in V1, PRD §5.1); the version lives in the URL, so the body
# is immutable-cacheable.
_SDK_SCRIPT = (files("oriflux.ingest") / "static" / "oriflux.js").read_bytes()


def _do_not_track(request: Request) -> bool:
    """DNT/GPC honored at ingestion (PRD §9)."""
    return request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1"


def _locale(request: Request) -> str:
    accept = request.headers.get("accept-language", "")
    first = accept.split(",")[0].strip()
    return first.split(";")[0].strip()


def _client_ip(request: Request) -> str:
    # Walk X-Forwarded-For from the RIGHT and return the first globally
    # routable address. Everything to the right of the caller was appended
    # by our own trusted hops (NPM, the products' first-party /of proxies —
    # private/cluster addresses); leftmost values are attacker-controlled.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",")]
        for hop in reversed(hops):
            try:
                if ipaddress.ip_address(hop).is_global:
                    return hop
            except ValueError:
                continue
        return hops[-1]  # all private (dev/test): the nearest peer
    return request.client.host if request.client else "unknown"


def create_app(
    redis: Redis | None = None,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    setup_logging()
    settings = settings or get_settings()

    def wire_state(
        app: FastAPI, redis_client: Redis, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        app.state.redis = redis_client
        app.state.session_factory = factory
        app.state.resolver = IngestKeyResolver(
            factory, cache_ttl_s=settings.api_key_cache_ttl_s
        )
        app.state.rate_limiter = RateLimiter(
            redis_client,
            per_key=settings.ingest_rate_limit_per_key,
            per_ip=settings.ingest_rate_limit_per_ip,
        )
        app.state.geo = GeoResolver(settings.geoip_dir)
        app.state.visitor_hasher = VisitorHasher(redis_client)
        app.state.session_tracker = SessionTracker(redis_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis_client = redis or Redis.from_url(settings.redis_url)
        engine = None
        if session_factory is None:
            engine = create_engine(settings)
            factory = create_session_factory(engine)
        else:
            factory = session_factory
        wire_state(app, redis_client, factory)
        yield
        await redis_client.aclose()
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="oriflux_ingest", lifespan=lifespan)
    # Cross-origin collection from any instrumented site: auth is the Bearer
    # key (no cookies/credentials), so a wildcard origin is safe. Preflights
    # are cached a day to keep the per-pageview cost at one request.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=86400,
    )
    # For test transports that skip lifespan, wire the injected boundaries anyway.
    if redis is not None and session_factory is not None:
        wire_state(app, redis, session_factory)

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
        payload: Annotated[
            PageviewIn | CustomEventIn | IdentifyIn | VitalIn,
            Field(discriminator="type"),
        ],
        request: Request,
        key: ResolvedIngestKey = Depends(authenticate),
    ) -> dict[str, Any]:
        if _do_not_track(request):
            return {"tracked": False}

        now = datetime.now(tz=UTC)
        # The IP lives only in these two local variables: resolved to geo and
        # hashed into the daily visitor id, then discarded (PRD §9).
        ip = _client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        visitor_hash = await request.app.state.visitor_hasher.visitor_hash(
            key.project_id, ip, user_agent, day=now.date()
        )
        tracker: SessionTracker = request.app.state.session_tracker
        session_id = await tracker.session_for(visitor_hash)

        if isinstance(payload, IdentifyIn):
            # No event row: identify only binds the session, server side (#17).
            await tracker.identify(session_id, payload.user_id)
            return {"identified": True}

        inline_user = payload.user_id if isinstance(payload, CustomEventIn) else ""
        user_pseudo_id = inline_user or await tracker.user_for(session_id)
        geo = request.app.state.geo.resolve(ip)
        ua_class, crawler_name = classify_traffic(user_agent)
        traffic_class, class_reason = refine_traffic(
            ua_class,
            crawler_name,
            user_agent=user_agent,
            asn=geo.asn,
            events_last_minute=await tracker.cadence(visitor_hash),
        )
        enrichment: dict[str, Any] = {
            "org_id": key.org_id,
            "project_id": key.project_id,
            "timestamp": now,
            "geo": geo,
            "ua": parse_ua(user_agent),
            "traffic_class": traffic_class,
            "class_reason": class_reason,
            "visitor_hash": visitor_hash,
            "session_id": session_id,
            "locale": _locale(request),
            "user_pseudo_id": user_pseudo_id,
        }
        if isinstance(payload, PageviewIn):
            event = EnrichedEvent.from_pageview(payload, **enrichment)
        elif isinstance(payload, VitalIn):
            event = EnrichedEvent.from_vital(payload, **enrichment)
        else:
            event = EnrichedEvent.from_custom_event(payload, **enrichment)
        await publish_event(request.app.state.redis, event)
        return {"event_id": str(event.event_id)}

    @app.post("/api/v1/api-metrics", status_code=202)
    async def collect_api_metrics(
        payload: ApiMetricsIn,
        request: Request,
        key: ResolvedIngestKey = Depends(authenticate),
    ) -> dict[str, Any]:
        """Aggregate payload from oriflux-sdk (§5.3). Each entry's caller IP
        is resolved to country/ASN here and discarded — ApiMinuteRow has no
        IP field, so nothing downstream can ever see the address."""
        geo = request.app.state.geo
        rows = [
            ApiMinuteRow.from_entry(
                entry,
                window_start=payload.window_start,
                org_id=key.org_id,
                project_id=key.project_id,
                source_id=key.source_id,
                geo=geo.resolve(entry.ip) if entry.ip else GeoInfo(),
            )
            for entry in payload.entries
        ]
        if rows:
            await publish_api_rows(request.app.state.redis, rows)
        return {"accepted": len(rows)}

    @app.post("/api/v1/connectors/{connector_id}/webhook", status_code=202)
    async def billing_webhook(connector_id: uuid.UUID, request: Request) -> dict[str, Any]:
        """Stripe / Lemon Squeezy webhooks (issue #24). Signature-verified;
        idempotent under redelivery via deterministic event UUIDs (uuid5 of
        the provider event id — the ClickHouse dedup absorbs duplicates)."""
        if not settings.fernet_key:
            raise HTTPException(status_code=503, detail="connectors disabled (no Fernet key)")
        async with request.app.state.session_factory() as session:
            connector = await session.get(Connector, connector_id)
        if connector is None:
            raise HTTPException(status_code=404, detail="unknown connector")
        secret = decrypt_secret(connector.webhook_secret_encrypted, settings.fernet_key)
        body = await request.body()
        if connector.provider == ConnectorProvider.stripe:
            header = request.headers.get("stripe-signature", "")
            if not verify_stripe_signature(body, header, secret):
                raise HTTPException(status_code=401, detail="invalid signature")
            revenue = map_stripe_event(json.loads(body))
        else:
            signature = request.headers.get("x-signature", "")
            if not verify_lemonsqueezy_signature(body, signature, secret):
                raise HTTPException(status_code=401, detail="invalid signature")
            revenue = map_lemonsqueezy_event(json.loads(body))
        if revenue is None:
            return {"ignored": True}
        event = EnrichedEvent(
            event_id=revenue.event_id,
            timestamp=datetime.now(tz=UTC),
            org_id=str(connector.org_id),
            project_id=str(connector.project_id),
            source_type="api",
            event_name=revenue.name,
            value=revenue.amount,
            props=revenue.props,
        )
        await publish_event(request.app.state.redis, event)
        return {"event_id": str(event.event_id)}

    @app.get("/v1/oriflux.js")
    async def sdk_script() -> Response:
        return Response(
            content=_SDK_SCRIPT,
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=604800, immutable"},
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
