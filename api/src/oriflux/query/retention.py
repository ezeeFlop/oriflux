"""Typed retention cohorts (issue #20, PRD §5.2).

Décision 2026-07-10: identified users ONLY — the daily salt makes
anonymous cross-day retention mathematically impossible, by design.
Cohort = the bucket (Monday week or month) of a user's first activation
event in the period; retention = distinct returning users per offset.
Registry discipline: vetted fragments, bound values, org always scoped.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from oriflux.models.events import _EVENT_NAME_RE
from oriflux.query.models import Period

# toDateTime: keep DateTime64 quirks out (same lesson as windowFunnel, #19)
_BUCKETS: dict[str, tuple[str, str]] = {
    "week": ("toStartOfWeek(toDateTime(timestamp), 1)", "dateDiff('week', cohort, bucket)"),
    "month": ("toStartOfMonth(toDateTime(timestamp))", "dateDiff('month', cohort, bucket)"),
}


class RetentionRequest(BaseModel):
    activation_event: str = Field(min_length=1, max_length=64)
    granularity: Literal["week", "month"] = "week"
    project_id: str | None = None
    period: Period

    @field_validator("activation_event")
    @classmethod
    def _activation_is_a_slug(cls, value: str) -> str:
        if not _EVENT_NAME_RE.match(value):
            raise ValueError("activation event must be an event-name slug")
        return value


def build_retention(request: RetentionRequest, *, org_id: str) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "org_id": org_id,
        "start": request.period.start,
        "end": request.period.end,
        "activation": request.activation_event,
    }
    scope = [
        "org_id = {org_id:String}",
        "timestamp >= {start:DateTime64(3)}",
        "timestamp < {end:DateTime64(3)}",
        "user_pseudo_id != ''",
    ]
    if request.project_id is not None:
        params["project_id"] = request.project_id
        scope.append("project_id = {project_id:String}")
    where = " AND ".join(scope)

    bucket_sql, offset_sql = _BUCKETS[request.granularity]
    sql = (
        f"WITH activation AS ("
        f"SELECT user_pseudo_id, min({bucket_sql}) AS cohort FROM events "
        f"WHERE {where} AND event_name = {{activation:String}} "
        f"GROUP BY user_pseudo_id), "
        f"activity AS ("
        f"SELECT DISTINCT user_pseudo_id, {bucket_sql} AS bucket FROM events "
        f"WHERE {where}) "
        f"SELECT toString(cohort) AS cohort_start, {offset_sql} AS offset, "
        f"uniq(user_pseudo_id) AS users "
        f"FROM activation INNER JOIN activity USING user_pseudo_id "
        f"WHERE bucket >= cohort "
        f"GROUP BY cohort, offset ORDER BY cohort, offset"
    )
    return sql, params
