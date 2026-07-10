"""The typed query object — the single query contract (PRD §8.3).

Validation against the registry happens here, at schema level: a request
naming an unknown metric or dimension never reaches SQL building, and the
error message lists what IS available (Ask Oriflux and MCP clients repair
themselves from these messages).
"""

from datetime import datetime as _datetime
from datetime import timedelta
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from oriflux.query.registry import DIMENSIONS, METRICS

_HOUR_GRANULARITY_MAX = timedelta(days=31)


class Period(BaseModel):
    start: _datetime
    end: _datetime

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("period end must be after start")
        return self


class Filter(BaseModel):
    dimension: str
    op: Literal["eq", "neq", "in"]
    value: str | list[str]

    @field_validator("dimension")
    @classmethod
    def _known_dimension(cls, value: str) -> str:
        if value not in DIMENSIONS:
            raise ValueError(
                f"unknown dimension: {value!r} — available: {', '.join(sorted(DIMENSIONS))}"
            )
        return value


class QueryRequest(BaseModel):
    metric: str
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    granularity: Literal["hour", "day", "week", "month"] | None = None
    period: Period
    compare_to: Literal["previous_period", "previous_year"] | None = None

    @field_validator("metric")
    @classmethod
    def _known_metric(cls, value: str) -> str:
        if value not in METRICS:
            raise ValueError(
                f"unknown metric: {value!r} — available: {', '.join(sorted(METRICS))}"
            )
        return value

    @field_validator("dimensions")
    @classmethod
    def _known_dimensions(cls, value: list[str]) -> list[str]:
        for name in value:
            if name not in DIMENSIONS:
                raise ValueError(
                    f"unknown dimension: {name!r} — available: {', '.join(sorted(DIMENSIONS))}"
                )
        return value

    @model_validator(mode="after")
    def _dimensions_must_match_the_metric_source(self) -> Self:
        source = METRICS[self.metric].source
        compatible = sorted(n for n, d in DIMENSIONS.items() if source in d.sources)
        for name in [*self.dimensions, *(f.dimension for f in self.filters)]:
            if source not in DIMENSIONS[name].sources:
                raise ValueError(
                    f"dimension {name!r} is not available for metric {self.metric!r} — "
                    f"available: {', '.join(compatible)}"
                )
        return self

    @model_validator(mode="after")
    def _hour_granularity_needs_a_short_period(self) -> Self:
        if (
            self.granularity == "hour"
            and self.period.end - self.period.start > _HOUR_GRANULARITY_MAX
        ):
            raise ValueError(
                "granularity 'hour' is limited to periods of 31 days or less — "
                "use 'day', 'week' or 'month' for longer ranges"
            )
        return self
