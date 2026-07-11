"""Compile a validated QueryRequest into parameterized ClickHouse SQL.

Only registry fragments appear in the SQL text; every user-supplied value
is bound as a server-side parameter ({name:Type}). `FROM events FINAL`
makes counts correct under the at-least-once/ReplacingMergeTree dedup
scheme even before background merges collapse duplicate UUIDs.

Event-shaped metrics aggregate `events` directly. Session-shaped metrics
aggregate a per-session rollup: the inner query groups the same filtered
events by session_id, exposing session start (timestamp), pageview_count,
duration_s, and any(dimension) for whatever the outer query needs.
"""

from typing import Any

from oriflux.query.models import Filter, QueryRequest
from oriflux.query.registry import DIMENSIONS, GRANULARITY_SQL, METRICS, MetricSpec

_OPS = {"eq": "=", "neq": "!=", "in": "IN"}


def _filter_clause(f: Filter, index: int, params: dict[str, Any]) -> str:
    spec = DIMENSIONS[f.dimension]
    name = f"filter_{index}"
    if f.op == "in":
        values = f.value if isinstance(f.value, list) else [f.value]
        params[name] = values
        return f"{spec.sql} IN {{{name}:Array(String)}}"
    params[name] = f.value
    if f.op == "prefix":
        return f"startsWith({spec.sql}, {{{name}:String}})"
    return f"{spec.sql} {_OPS[f.op]} {{{name}:String}}"


def _where(
    request: QueryRequest, metric: MetricSpec, params: dict[str, Any], *, time_column: str
) -> str:
    clauses = [
        "org_id = {org_id:String}",
        f"{time_column} >= {{start:DateTime64(3)}}",
        f"{time_column} < {{end:DateTime64(3)}}",
    ]
    if metric.event_filter is not None:
        clauses.append(metric.event_filter)
    for i, f in enumerate(request.filters):
        clauses.append(_filter_clause(f, i, params))
    return " AND ".join(clauses)


def _select_and_group(
    request: QueryRequest,
    value_sql: str,
    *,
    dimension_sql: dict[str, str],
    time_column: str,
) -> tuple[str, str]:
    """SELECT list + GROUP BY/ORDER BY tail shared by both shapes."""
    select: list[str] = []
    group_by: list[str] = []
    if request.granularity is not None:
        bucket = GRANULARITY_SQL[request.granularity].format(col=time_column)
        select.append(f"{bucket} AS bucket")
        group_by.append("bucket")
    for name in request.dimensions:
        select.append(f"{dimension_sql[name]} AS {name}")
        group_by.append(name)
    select.append(f"{value_sql} AS value")
    tail = f" GROUP BY {', '.join(group_by)} ORDER BY {', '.join(group_by)}" if group_by else ""
    return ", ".join(select), tail


def build_query(request: QueryRequest, *, org_id: str) -> tuple[str, dict[str, Any]]:
    metric = METRICS[request.metric]
    params: dict[str, Any] = {
        "org_id": org_id,
        "start": request.period.start,
        "end": request.period.end,
    }
    time_column = "timestamp" if metric.source == "events" else "timestamp_min"
    where = _where(request, metric, params, time_column=time_column)
    columns = {name: DIMENSIONS[name].sql for name in request.dimensions}

    if metric.shape == "event":
        select, tail = _select_and_group(
            request, metric.sql, dimension_sql=columns, time_column="timestamp"
        )
        return f"SELECT {select} FROM events FINAL WHERE {where}{tail}", params

    if metric.shape in ("api", "api_latency"):
        select, tail = _select_and_group(
            request, metric.sql, dimension_sql=columns, time_column="timestamp_min"
        )
        array_join = (
            " ARRAY JOIN latency_bucket_ms AS lat_ms, latency_counts AS lat_cnt"
            if metric.shape == "api_latency"
            else ""
        )
        return (
            f"SELECT {select} FROM api_minutely FINAL{array_join} WHERE {where}{tail}",
            params,
        )

    # session shape: per-session rollup first, aggregate on top
    inner_select = [
        "session_id",
        "min(timestamp) AS session_start",  # drives the outer time bucket
        "count() AS pageview_count",
        "date_diff('second', min(timestamp), max(timestamp)) AS duration_s",
    ]
    # dim_ prefix: a bare alias like `any(country) AS country` would shadow
    # the real column inside the same query's WHERE (ILLEGAL_AGGREGATION)
    for name in request.dimensions:
        inner_select.append(f"any({DIMENSIONS[name].sql}) AS dim_{name}")
    inner = (
        f"SELECT {', '.join(inner_select)} FROM events FINAL "
        f"WHERE {where} AND session_id != '' GROUP BY session_id"
    )
    outer_columns = {name: f"dim_{name}" for name in request.dimensions}
    select, tail = _select_and_group(
        request, metric.sql, dimension_sql=outer_columns, time_column="session_start"
    )
    return f"SELECT {select} FROM ({inner}){tail}", params
