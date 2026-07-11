"""Traffic-classification API (issue #42, PRD §15.2).

Oriflux is the single source of truth for the crawler/AI-agent list;
AudiGEO becomes a consumer of THIS endpoint. The list is versioned with
an ETag so consumers cache cheaply; `classify` runs the same
refine_traffic path the ingest uses.
"""

import hashlib
import json

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel

from oriflux.api.deps import require_read_key_org
from oriflux.enrichment.crawlers import (
    AI_AGENT_PATTERNS,
    BOT_PATTERNS,
    classify_traffic,
    refine_traffic,
)

router = APIRouter(prefix="/api/v1/classification", tags=["classification"])


def _canonical_list() -> dict[str, object]:
    crawlers = (
        [{"pattern": p, "name": n, "class": "ai_agent"} for p, n in AI_AGENT_PATTERNS.items()]
        + [{"pattern": p, "name": n, "class": "bot"} for p, n in BOT_PATTERNS.items()]
    )
    crawlers.sort(key=lambda c: (c["class"], c["name"]))
    version = hashlib.sha256(
        json.dumps(crawlers, sort_keys=True).encode()
    ).hexdigest()[:12]
    return {"version": version, "crawlers": crawlers}


class ClassifyIn(BaseModel):
    user_agent: str


@router.get("/crawlers", response_model=None)
async def crawlers(
    response: Response,
    if_none_match: str | None = Header(default=None),
    org_id: str = Depends(require_read_key_org),
) -> dict[str, object] | Response:
    payload = _canonical_list()
    etag = f'"{payload["version"]}"'
    if if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=3600"
    return payload


@router.post("/classify")
async def classify(
    payload: ClassifyIn,
    org_id: str = Depends(require_read_key_org),
) -> dict[str, str]:
    ua_class, crawler = classify_traffic(payload.user_agent)
    traffic_class, reason = refine_traffic(
        ua_class, crawler, user_agent=payload.user_agent
    )
    return {"traffic_class": traffic_class, "reason": reason}
