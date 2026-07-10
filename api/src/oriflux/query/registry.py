"""Hand-maintained metric/dimension registry (PRD §8.3).

Every name maps to a vetted SQL fragment. This registry is the ONLY place
SQL fragments for analytics queries may live — dashboard, REST, MCP and Ask
Oriflux all compile through it. Fragments are constants, never derived from
user input; user values travel as bound parameters.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DimensionSpec:
    name: str
    sql: str  # column expression, vetted


@dataclass(frozen=True)
class MetricSpec:
    name: str
    sql: str  # aggregate expression, vetted
    event_filter: str | None  # vetted WHERE fragment selecting the metric's events
    allowed_dimensions: frozenset[str]


DIMENSIONS: dict[str, DimensionSpec] = {
    "project_id": DimensionSpec(name="project_id", sql="project_id"),
    "country": DimensionSpec(name="country", sql="country"),
}

METRICS: dict[str, MetricSpec] = {
    "pageviews": MetricSpec(
        name="pageviews",
        sql="count()",
        event_filter="event_name = 'pageview'",
        allowed_dimensions=frozenset(DIMENSIONS),
    ),
}

GRANULARITY_SQL: dict[str, str] = {
    "hour": "toStartOfHour(timestamp)",
    "day": "toStartOfDay(timestamp)",
    "month": "toStartOfMonth(timestamp)",
}
