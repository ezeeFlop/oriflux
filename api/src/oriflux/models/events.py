"""Event models shared by ingest, workers, and the ClickHouse row shape.

`PageviewIn` is the wire contract (what SDKs POST); `EnrichedEvent` is the
internal event as buffered in Redis Streams and inserted into ClickHouse.
The full enrichment pipeline (geo, UA, bot classification, visitor hash)
lands with issue #4 — the shape carries every §8.4 column from day one so
no backfill is ever needed.
"""

import json
import re
from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from oriflux.models.enrichment import GeoInfo, UAInfo

# §9: identify() accepts only pseudonymous IDs — PII dies at validation,
# with a message naming the reason so integrators can fix their call site.
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE_RE = re.compile(r"^\+?[0-9 ().-]{8,}$")

_EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PROPS_MAX_KEYS = 32
_PROPS_MAX_BYTES = 4096


def _reject_pii(value: str, *, where: str) -> str:
    if _EMAIL_RE.search(value):
        raise ValueError(f"{where} looks like an email address — send a pseudonymous id")
    if _PHONE_RE.match(value) and sum(c.isdigit() for c in value) >= 8:
        raise ValueError(f"{where} looks like a phone number — send a pseudonymous id")
    return value


def _validate_props(props: dict[str, Any]) -> dict[str, Any]:
    if len(props) > _PROPS_MAX_KEYS:
        raise ValueError(f"props may hold at most {_PROPS_MAX_KEYS} keys")
    if len(json.dumps(props, separators=(",", ":"))) > _PROPS_MAX_BYTES:
        raise ValueError(f"props exceed {_PROPS_MAX_BYTES} bytes serialized")
    return props


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


class CustomEventIn(BaseModel):
    """A product-analytics event: oriflux.track(name, props) (§5.2, #17)."""

    type: Literal["event"]
    name: str
    url: str = ""
    props: dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(default="", max_length=128)

    @field_validator("name")
    @classmethod
    def _name_must_be_a_slug(cls, value: str) -> str:
        if not _EVENT_NAME_RE.match(value):
            raise ValueError("event name must match ^[a-z][a-z0-9_]{0,63}$")
        if value == "pageview":
            raise ValueError("'pageview' is reserved for the pageview event type")
        return value

    @field_validator("url")
    @classmethod
    def _url_must_be_http_when_present(cls, value: str) -> str:
        if value:
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("url must be an absolute http(s) URL")
        return value

    @field_validator("props")
    @classmethod
    def _props_within_caps(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_props(value)

    @field_validator("user_id")
    @classmethod
    def _user_id_must_be_pseudonymous(cls, value: str) -> str:
        return _reject_pii(value, where="user_id") if value else value

    @property
    def url_path(self) -> str:
        return (urlsplit(self.url).path or "/") if self.url else ""


class VitalIn(BaseModel):
    """A Web Vital sample reported by oriflux.js (§5.1, #23)."""

    type: Literal["vital"]
    name: Literal["lcp", "cls", "inp", "ttfb"]
    value: float = Field(ge=0, le=600_000)  # ms for lcp/inp/ttfb, unitless for cls
    url: str

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


class IdentifyIn(BaseModel):
    """oriflux.identify(user_id, traits) — pseudonymous only (§5.2, §9, #17)."""

    type: Literal["identify"]
    user_id: str = Field(min_length=1, max_length=128)
    traits: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_id")
    @classmethod
    def _user_id_must_be_pseudonymous(cls, value: str) -> str:
        return _reject_pii(value, where="user_id")

    @field_validator("traits")
    @classmethod
    def _traits_within_caps_and_pseudonymous(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_props(value)
        for key, trait in value.items():
            if isinstance(trait, str):
                _reject_pii(trait, where=f"trait {key!r}")
        return value


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
    class_reason: str = ""  # explainable classification (#21): ua:<name> | heuristic:<name>
    value: float = 0.0  # numeric payload (Web Vitals #23); 0 for plain events
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
        user_pseudo_id: str = "",
        class_reason: str = "",
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
            class_reason=class_reason,
            visitor_hash=visitor_hash,
            session_id=session_id,
            user_pseudo_id=user_pseudo_id,
            props=wire.props,
        )

    @classmethod
    def from_vital(
        cls,
        wire: "VitalIn",
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
        user_pseudo_id: str = "",
        class_reason: str = "",
    ) -> Self:
        geo = geo or GeoInfo()
        ua = ua or UAInfo()
        return cls(
            event_id=uuid4(),
            timestamp=timestamp,
            org_id=org_id,
            project_id=project_id,
            source_type="web",
            event_name=f"vital_{wire.name}",
            url_path=wire.url_path,
            country=geo.country,
            region=geo.region,
            city=geo.city,
            asn=geo.asn,
            device=ua.device,
            os=ua.os,
            browser=ua.browser,
            locale=locale,
            traffic_class=traffic_class,
            class_reason=class_reason,
            visitor_hash=visitor_hash,
            session_id=session_id,
            user_pseudo_id=user_pseudo_id,
            value=wire.value,
        )

    @classmethod
    def from_custom_event(
        cls,
        wire: CustomEventIn,
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
        user_pseudo_id: str = "",
        class_reason: str = "",
    ) -> Self:
        geo = geo or GeoInfo()
        ua = ua or UAInfo()
        return cls(
            event_id=uuid4(),
            timestamp=timestamp,
            org_id=org_id,
            project_id=project_id,
            source_type="web",
            event_name=wire.name,
            url_path=wire.url_path,
            country=geo.country,
            region=geo.region,
            city=geo.city,
            asn=geo.asn,
            device=ua.device,
            os=ua.os,
            browser=ua.browser,
            locale=locale,
            traffic_class=traffic_class,
            class_reason=class_reason,
            visitor_hash=visitor_hash,
            session_id=session_id,
            user_pseudo_id=user_pseudo_id,
            props=wire.props,
        )
