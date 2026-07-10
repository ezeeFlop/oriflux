"""Event models shared by ingest, workers, and the ClickHouse row shape.

`PageviewIn` is the wire contract (what SDKs POST); `EnrichedEvent` is the
internal event as buffered in Redis Streams and inserted into ClickHouse.
The full enrichment pipeline (geo, UA, bot classification, visitor hash)
lands with issue #4 — the shape carries every §8.4 column from day one so
no backfill is ever needed.
"""

from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from oriflux.models.enrichment import GeoInfo, UAInfo


class PageviewIn(BaseModel):
    """A pageview as posted by oriflux.js or the direct HTTP endpoint."""

    type: Literal["pageview"]
    url: str
    referrer: str = ""
    props: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        return value

    @property
    def url_path(self) -> str:
        return urlsplit(self.url).path or "/"

    def utm_params(self) -> dict[str, str]:
        """First value of each utm_* query param, parsed once."""
        query = parse_qs(urlsplit(self.url).query)
        return {
            param: values[0]
            for param, values in query.items()
            if param.startswith("utm_") and values
        }


class EnrichedEvent(BaseModel):
    """One row of the ClickHouse `events` table (PRD §8.4)."""

    event_id: UUID
    timestamp: datetime
    org_id: str
    project_id: str
    source_type: Literal["web", "app", "api"]
    event_name: str
    visitor_hash: str = ""
    session_id: str = ""
    user_pseudo_id: str = ""
    tenant_id: str = ""
    url_path: str = ""
    referrer: str = ""
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_term: str = ""
    utm_content: str = ""
    country: str = ""
    region: str = ""
    city: str = ""
    asn: int = 0
    device: str = ""
    os: str = ""
    browser: str = ""
    locale: str = ""
    # "" = unclassified; classification (issue #4) fills it, but the column exists from day one
    traffic_class: Literal["", "human", "bot", "ai_agent"] = ""
    props: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_pageview(
        cls,
        wire: PageviewIn,
        *,
        org_id: str,
        project_id: str,
        timestamp: datetime,
        geo: GeoInfo | None = None,
        ua: UAInfo | None = None,
        traffic_class: Literal["", "human", "bot", "ai_agent"] = "",
        visitor_hash: str = "",
        session_id: str = "",
        locale: str = "",
    ) -> Self:
        geo = geo or GeoInfo()
        ua = ua or UAInfo()
        utm = wire.utm_params()
        return cls(
            event_id=uuid4(),
            timestamp=timestamp,
            org_id=org_id,
            project_id=project_id,
            source_type="web",
            event_name="pageview",
            url_path=wire.url_path,
            referrer=wire.referrer,
            utm_source=utm.get("utm_source", ""),
            utm_medium=utm.get("utm_medium", ""),
            utm_campaign=utm.get("utm_campaign", ""),
            utm_term=utm.get("utm_term", ""),
            utm_content=utm.get("utm_content", ""),
            country=geo.country,
            region=geo.region,
            city=geo.city,
            asn=geo.asn,
            device=ua.device,
            os=ua.os,
            browser=ua.browser,
            locale=locale,
            traffic_class=traffic_class,
            visitor_hash=visitor_hash,
            session_id=session_id,
            props=wire.props,
        )
