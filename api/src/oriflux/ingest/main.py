"""oriflux_ingest — stateless collection service.

POST /api/v1/events: Bearer-key auth → Pydantic validation → UUID
assignment → Redis Streams buffer. Enrichment (geo, UA, bot classification,
visitor hash) plugs into this path with issue #4.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request
from redis.asyncio import Redis

from oriflux.auth import require_bearer_key
from oriflux.config import Settings, get_settings
from oriflux.models.events import EnrichedEvent, PageviewIn
from oriflux.storage.redis_stream import publish_event


def create_app(redis: Redis | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.redis = redis or Redis.from_url(settings.redis_url)
        yield
        await app.state.redis.aclose()

    app = FastAPI(title="oriflux_ingest", lifespan=lifespan)
    # For test transports that skip lifespan, make the injected client available anyway.
    if redis is not None:
        app.state.redis = redis

    require_ingest_key = require_bearer_key(settings.ingest_api_key)

    @app.post("/api/v1/events", status_code=202, dependencies=[Depends(require_ingest_key)])
    async def collect(pageview: PageviewIn, request: Request) -> dict[str, str]:
        event = EnrichedEvent.from_pageview(
            pageview,
            org_id=settings.org_id,
            project_id=settings.project_id,
            timestamp=datetime.now(tz=UTC),
        )
        await publish_event(request.app.state.redis, event)
        return {"event_id": str(event.event_id)}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
