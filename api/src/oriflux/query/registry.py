"""Hand-maintained metric/dimension registry (PRD §8.3, grown by issue #6).

Every name maps to a vetted SQL fragment. This registry is the ONLY place
SQL fragments for analytics queries may live — dashboard, REST, MCP and Ask
Oriflux all compile through it. Fragments are constants, never derived from
user input; user values travel as bound parameters.

Two query shapes:
- "event"   — aggregate straight over `events`.
- "session" — aggregate over a per-session rollup (GROUP BY session_id);
  the engine builds the inner query, these fragments aggregate its columns
  (pageview_count, duration_s, timestamp = session start, any(dim)).

Cross-day caveat (PRD §9, décision 2026-07-10): the visitor hash rotates
daily, so `visitors` summed over multiple days counts VISIT-DAYS, not
distinct people — within one day it dedupes exactly. Surfaces must label
multi-day totals accordingly.
"""

from dataclasses import dataclass
from typing import Literal

QueryShape = Literal["event", "session"]


@dataclass(frozen=True)
class DimensionSpec:
    name: str
    sql: str  # column expression on `events`, vetted


@dataclass(frozen=True)
class MetricSpec:
    name: str
    shape: QueryShape
    sql: str  # vetted aggregate expression for the shape's source
    event_filter: str | None = None  # vetted WHERE fragment on `events`


DIMENSIONS: dict[str, DimensionSpec] = {
    "project_id": DimensionSpec(name="project_id", sql="project_id"),
    "country": DimensionSpec(name="country", sql="country"),
    "region": DimensionSpec(name="region", sql="region"),
    "city": DimensionSpec(name="city", sql="city"),
    "asn": DimensionSpec(name="asn", sql="asn"),
    "page": DimensionSpec(name="page", sql="url_path"),
    "referrer": DimensionSpec(name="referrer", sql="referrer"),
    "utm_source": DimensionSpec(name="utm_source", sql="utm_source"),
    "utm_medium": DimensionSpec(name="utm_medium", sql="utm_medium"),
    "utm_campaign": DimensionSpec(name="utm_campaign", sql="utm_campaign"),
    "device": DimensionSpec(name="device", sql="device"),
    "os": DimensionSpec(name="os", sql="os"),
    "browser": DimensionSpec(name="browser", sql="browser"),
    "locale": DimensionSpec(name="locale", sql="locale"),
    "traffic_class": DimensionSpec(name="traffic_class", sql="traffic_class"),
}

_PAGEVIEWS = "event_name = 'pageview'"

METRICS: dict[str, MetricSpec] = {
    "pageviews": MetricSpec(name="pageviews", shape="event", sql="count()",
                            event_filter=_PAGEVIEWS),
    # dedupes by hash within a day; multi-day totals are visit-days (see module doc)
    "visitors": MetricSpec(name="visitors", shape="event", sql="uniq(visitor_hash)",
                           event_filter=_PAGEVIEWS),
    "sessions": MetricSpec(name="sessions", shape="session", sql="count()",
                           event_filter=_PAGEVIEWS),
    # % of sessions with exactly one pageview
    "bounce_rate": MetricSpec(
        name="bounce_rate", shape="session",
        sql="round(100 * countIf(pageview_count = 1) / count(), 1)",
        event_filter=_PAGEVIEWS,
    ),
    # average session length in seconds
    "session_duration": MetricSpec(
        name="session_duration", shape="session",
        sql="round(avg(duration_s), 1)",
        event_filter=_PAGEVIEWS,
    ),
}

# {col} is filled by the engine with the shape's time column (a registry
# constant — never user input): `timestamp` for events, `session_start` for
# the session rollup.
GRANULARITY_SQL: dict[str, str] = {
    "hour": "toStartOfHour({col})",
    "day": "toStartOfDay({col})",
    "week": "toStartOfWeek({col}, 1)",  # weeks start Monday
    "month": "toStartOfMonth({col})",
}
