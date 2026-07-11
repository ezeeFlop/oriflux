"""Typed funnel query → ClickHouse windowFunnel (issue #19, PRD §5.2).

Same contract discipline as the registry: every SQL fragment below is a
vetted constant, user values travel as bound parameters, org scoping is
always applied. Décision 2026-07-10: the anonymous scope groups by
session_id and cannot exceed a 24 h window (the daily salt makes
cross-day anonymous sequences impossible by design — surfaces label it
"session-scoped"); the identified scope groups by user_pseudo_id and
allows multi-day windows.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from oriflux.models.events import _EVENT_NAME_RE
from oriflux.query.models import Period
from oriflux.query.registry import DIMENSIONS

_SESSION_MAX_HOURS = 24
_IDENTIFIED_MAX_HOURS = 30 * 24
_SEGMENT_LIMIT = 25


class FunnelStep(BaseModel):
    kind: Literal["event", "page"]
    target: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _target_matches_kind(self) -> "FunnelStep":
        if self.kind == "event" and not _EVENT_NAME_RE.match(self.target):
            raise ValueError("event step target must be an event-name slug")
        if self.kind == "page" and not self.target.startswith("/"):
            raise ValueError("page step target must be a path starting with /")
        return self


class FunnelRequest(BaseModel):
    steps: list[FunnelStep] = Field(min_length=2, max_length=8)
    scope: Literal["session", "identified"] = "session"
    window_hours: int | None = Field(default=None, ge=1)
    segment_by: str | None = None
    project_id: str | None = None
    period: Period

    @field_validator("segment_by")
    @classmethod
    def _segment_is_an_events_dimension(cls, value: str | None) -> str | None:
        if value is None:
            return value
        spec = DIMENSIONS.get(value)
        if spec is None or "events" not in spec.sources:
            raise ValueError(f"unknown events dimension for segmentation: {value!r}")
        return value

    @model_validator(mode="after")
    def _window_fits_the_scope(self) -> "FunnelRequest":
        cap = _SESSION_MAX_HOURS if self.scope == "session" else _IDENTIFIED_MAX_HOURS
        if self.window_hours is None:
            self.window_hours = cap
        elif self.window_hours > cap:
            raise ValueError(
                f"{self.scope} funnels are capped at {cap} h — "
                "anonymous sequences cannot cross the daily salt rotation"
                if self.scope == "session"
                else f"identified funnels are capped at {cap} h"
            )
        return self


def _step_condition(step: FunnelStep, index: int, params: dict[str, Any]) -> str:
    name = f"step_{index}"
    params[name] = step.target
    if step.kind == "event":
        return f"event_name = {{{name}:String}}"
    return f"startsWith(url_path, {{{name}:String}})"


def build_funnel(request: FunnelRequest, *, org_id: str) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "org_id": org_id,
        "start": request.period.start,
        "end": request.period.end,
    }
    conditions = [
        _step_condition(step, i, params) for i, step in enumerate(request.steps)
    ]
    group_key = "session_id" if request.scope == "session" else "user_pseudo_id"
    assert request.window_hours is not None  # defaulted by validation
    window_s = int(request.window_hours) * 3600

    where = [
        "org_id = {org_id:String}",
        "timestamp >= {start:DateTime64(3)}",
        "timestamp < {end:DateTime64(3)}",
        f"({' OR '.join(conditions)})",
        f"{group_key} != ''",
    ]
    if request.project_id is not None:
        params["project_id"] = request.project_id
        where.append("project_id = {project_id:String}")

    segment_sql = DIMENSIONS[request.segment_by].sql if request.segment_by else None
    inner_select = [f"{group_key} AS funnel_key"]
    if segment_sql:
        inner_select.append(f"any({segment_sql}) AS segment")
    # toDateTime: CH 24.8's windowFunnel rejects DateTime64 timestamps
    inner_select.append(
        f"windowFunnel({window_s})(toDateTime(timestamp), {', '.join(conditions)}) AS level"
    )
    inner = (
        f"SELECT {', '.join(inner_select)} FROM events "
        f"WHERE {' AND '.join(where)} GROUP BY funnel_key"
    )

    step_counts = ", ".join(
        f"countIf(level >= {i + 1}) AS step_{i + 1}" for i in range(len(request.steps))
    )
    if segment_sql:
        sql = (
            f"SELECT segment, {step_counts} FROM ({inner}) "
            f"GROUP BY segment ORDER BY step_1 DESC LIMIT {_SEGMENT_LIMIT}"
        )
    else:
        sql = f"SELECT {step_counts} FROM ({inner})"
    return sql, params
