"""Compile a validated QueryRequest into parameterized ClickHouse SQL.

Only registry fragments appear in the SQL text; every user-supplied value is
bound as a server-side parameter ({name:Type}). `FROM events FINAL` makes
counts correct under the at-least-once/ReplacingMergeTree dedup scheme even
before background merges collapse duplicate UUIDs.
"""

from typing import Any

from oriflux.query.models import Filter, QueryRequest
from oriflux.query.registry import DIMENSIONS, GRANULARITY_SQL, METRICS

_OPS = {"eq": "=", "neq": "!=", "in": "IN"}


def _filter_clause(f: Filter, index: int, params: dict[str, Any]) -> str:
    spec = DIMENSIONS[f.dimension]
    name = f"filter_{index}"
    if f.op == "in":
        values = f.value if isinstance(f.value, list) else [f.value]
        params[name] = values
        return f"{spec.sql} IN {{{name}:Array(String)}}"
    params[name] = f.value
    return f"{spec.sql} {_OPS[f.op]} {{{name}:String}}"


def build_query(request: QueryRequest, *, org_id: str) -> tuple[str, dict[str, Any]]:
    metric = METRICS[request.metric]
    params: dict[str, Any] = {
        "org_id": org_id,
        "start": request.period.start,
        "end": request.period.end,
    }

    select: list[str] = []
    group_by: list[str] = []
    if request.granularity is not None:
        select.append(f"{GRANULARITY_SQL[request.granularity]} AS bucket")
        group_by.append("bucket")
    for name in request.dimensions:
        select.append(f"{DIMENSIONS[name].sql} AS {name}")
        group_by.append(name)
    select.append(f"{metric.sql} AS value")

    where = [
        "org_id = {org_id:String}",
        "timestamp >= {start:DateTime64(3)}",
        "timestamp < {end:DateTime64(3)}",
    ]
    if metric.event_filter is not None:
        where.append(metric.event_filter)
    for i, f in enumerate(request.filters):
        where.append(_filter_clause(f, i, params))

    sql = f"SELECT {', '.join(select)} FROM events FINAL WHERE {' AND '.join(where)}"
    if group_by:
        sql += f" GROUP BY {', '.join(group_by)} ORDER BY {', '.join(group_by)}"
    return sql, params
