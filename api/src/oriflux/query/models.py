"""The typed query object — the single query contract (PRD §8.3).

Validation against the registry happens here, at schema level: a request
naming an unknown metric or dimension never reaches SQL building.
"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from oriflux.query.registry import DIMENSIONS, METRICS


class Period(BaseModel):
    start: datetime
    end: datetime

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
            raise ValueError(f"unknown dimension: {value!r}")
        return value


class QueryRequest(BaseModel):
    metric: str
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    granularity: Literal["hour", "day", "month"] | None = None
    period: Period
    compare_to: Literal["previous_period"] | None = None

    @field_validator("metric")
    @classmethod
    def _known_metric(cls, value: str) -> str:
        if value not in METRICS:
            raise ValueError(f"unknown metric: {value!r}")
        return value

    @field_validator("dimensions")
    @classmethod
    def _known_dimensions(cls, value: list[str]) -> list[str]:
        for name in value:
            if name not in DIMENSIONS:
                raise ValueError(f"unknown dimension: {name!r}")
        return value

    @model_validator(mode="after")
    def _dimensions_allowed_for_metric(self) -> Self:
        allowed = METRICS[self.metric].allowed_dimensions
        for name in self.dimensions:
            if name not in allowed:
                raise ValueError(f"dimension {name!r} not allowed for metric {self.metric!r}")
        return self
