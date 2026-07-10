"""API-analytics models: the SDK's aggregate wire payload and the
ClickHouse `api_minutely` row shape (PRD §5.3 / §8.4).

The wire payload carries caller IPs as aggregation keys; ingest resolves
them to country/ASN and the row model has no IP field at all — the address
cannot survive past the ingest handler by construction.
"""

from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from oriflux.models.enrichment import GeoInfo


class ApiMetricEntryIn(BaseModel):
    endpoint: str = Field(max_length=200)
    method: str = Field(max_length=16)
    status_code: int = Field(ge=100, le=599)
    consumer: str = Field(default="", max_length=128)
    ip: str = Field(default="", max_length=64)
    count: int = Field(ge=1)
    bytes_in: int = Field(default=0, ge=0)
    bytes_out: int = Field(default=0, ge=0)
    latency_ms: dict[str, int] = Field(default_factory=dict)  # bucket → count
    overflow: bool = False


class ApiMetricsIn(BaseModel):
    window_start: datetime
    overflow_count: int = 0
    entries: list[ApiMetricEntryIn] = Field(max_length=4000)


class ApiMinuteRow(BaseModel):
    """One row of ClickHouse `api_minutely` — field order = column order."""

    entry_id: UUID
    timestamp_min: datetime
    org_id: str
    project_id: str
    source_id: str
    endpoint: str
    method: str
    status_code: int
    status_class: str  # 2xx|3xx|4xx|5xx
    consumer_id: str
    country: str
    asn: int
    count: int
    bytes_in: int
    bytes_out: int
    latency_bucket_ms: list[float]
    latency_counts: list[int]

    @classmethod
    def from_entry(
        cls,
        entry: ApiMetricEntryIn,
        *,
        window_start: datetime,
        org_id: str,
        project_id: str,
        source_id: str,
        geo: GeoInfo,
    ) -> Self:
        buckets = sorted((float(ms), n) for ms, n in entry.latency_ms.items())
        return cls(
            entry_id=uuid4(),
            timestamp_min=window_start.replace(second=0, microsecond=0),
            org_id=org_id,
            project_id=project_id,
            source_id=source_id,
            endpoint=entry.endpoint,
            method=entry.method,
            status_code=entry.status_code,
            status_class=f"{entry.status_code // 100}xx",
            consumer_id=entry.consumer,
            # overflow entries dropped their IP client-side: mark them honestly
            country="unresolved" if entry.overflow else geo.country,
            asn=geo.asn,
            count=entry.count,
            bytes_in=entry.bytes_in,
            bytes_out=entry.bytes_out,
            latency_bucket_ms=[b for b, _ in buckets],
            latency_counts=[n for _, n in buckets],
        )
