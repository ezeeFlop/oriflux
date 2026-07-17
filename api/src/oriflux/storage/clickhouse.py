"""ClickHouse access: schema, event sink (batcher side), query executor (API side).

`events` schema per PRD §8.4 — every column exists from the first event
(traffic_class included, populated by issue #4). ReplacingMergeTree keyed on
(org_id, project_id, timestamp, event_id) makes re-inserted event UUIDs
collapse: at-least-once delivery upstream, exactly-once counts downstream
(queries read FINAL).
"""

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any, Self

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from oriflux.config import Settings
from oriflux.models.api_metrics import ApiMinuteRow
from oriflux.models.events import EnrichedEvent

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id UUID,
    timestamp DateTime64(3, 'UTC'),
    org_id LowCardinality(String),
    project_id LowCardinality(String),
    source_type LowCardinality(String),
    event_name LowCardinality(String),
    visitor_hash String,
    session_id String,
    user_pseudo_id String,
    tenant_id String,
    url_path String,
    referrer String,
    utm_source String,
    utm_medium String,
    utm_campaign String,
    utm_term String,
    utm_content String,
    country LowCardinality(String),
    region LowCardinality(String),
    city String,
    asn UInt32,
    device LowCardinality(String),
    os LowCardinality(String),
    browser LowCardinality(String),
    locale LowCardinality(String),
    traffic_class LowCardinality(String),
    class_reason LowCardinality(String),
    value Float64,
    props String
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, project_id, timestamp, event_id)
TTL toDateTime(timestamp) + INTERVAL 13 MONTH
"""

# One source of truth for the column set: the EnrichedEvent model. Only the
# DDL above repeats it (ClickHouse types can't be derived from annotations).
API_MINUTELY_DDL = """
CREATE TABLE IF NOT EXISTS api_minutely (
    entry_id UUID,
    timestamp_min DateTime('UTC'),
    org_id LowCardinality(String),
    project_id LowCardinality(String),
    source_id LowCardinality(String),
    endpoint String,
    method LowCardinality(String),
    status_code UInt16,
    status_class LowCardinality(String),
    consumer_id String,
    country LowCardinality(String),
    asn UInt32,
    count UInt64,
    bytes_in UInt64,
    bytes_out UInt64,
    latency_bucket_ms Array(Float64),
    latency_counts Array(UInt64)
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(timestamp_min)
ORDER BY (org_id, project_id, timestamp_min, entry_id)
TTL timestamp_min + INTERVAL 13 MONTH
"""

_COLUMNS = list(EnrichedEvent.model_fields)
_PROPS_INDEX = _COLUMNS.index("props")  # props is JSON-encoded to a String column
_API_COLUMNS = list(ApiMinuteRow.model_fields)


def get_client(settings: Settings) -> Client:
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def ensure_schema(client: Client) -> None:
    client.command(EVENTS_DDL)
    client.command(API_MINUTELY_DDL)
    # Columns added after first ship (idempotent — CREATE IF NOT EXISTS above
    # only covers fresh installs): Web Vitals numeric payload (#23).
    client.command("ALTER TABLE events ADD COLUMN IF NOT EXISTS value Float64")
    # explainable bot classification (#21)
    client.command(
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS class_reason LowCardinality(String)"
    )


def wait_for_clickhouse(settings: Settings, *, attempts: int = 30, delay_s: float = 2.0) -> Client:
    last_error: Exception | None = None
    for _ in range(attempts):
        client = None
        try:
            client = get_client(settings)
            client.command("SELECT 1")
            return client
        except Exception as exc:  # noqa: BLE001 — any startup error means "not ready yet"
            last_error = exc
            # Close the failed attempt's client: a bare retry loop leaks a
            # socket per attempt, which is exactly what compounds the FD
            # exhaustion once the process is already near its open-file limit.
            if client is not None:
                with suppress(Exception):  # best-effort cleanup of the failed attempt
                    client.close()
            time.sleep(delay_s)
    raise RuntimeError(f"ClickHouse unreachable after {attempts} attempts") from last_error


@contextmanager
def clickhouse_session(settings: Settings, **kwargs: Any) -> Iterator[Client]:
    """A ready ClickHouse client, guaranteed closed on exit.

    The scheduled worker jobs run on a beat (evaluate_alerts every 60 s); a
    per-run client that is never closed leaks a urllib3 socket each tick and
    exhausts the container's open-file limit within a day (the prod Errno 24
    "Too many open files"). Jobs must use this, never a bare
    `wait_for_clickhouse`.
    """
    client = wait_for_clickhouse(settings, **kwargs)
    try:
        yield client
    finally:
        client.close()


class ClickHouseSink:
    """EventSink implementation used by the batcher."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def insert(self, events: list[EnrichedEvent]) -> None:
        rows = []
        for event in events:
            row = [getattr(event, column) for column in _COLUMNS]
            row[_PROPS_INDEX] = json.dumps(event.props)
            rows.append(row)
        self._client.insert("events", rows, column_names=_COLUMNS)


class ApiMinutelySink:
    """Sink for the api-metrics batcher (same dedup scheme as events)."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def insert(self, rows: list[ApiMinuteRow]) -> None:
        data = [[getattr(row, column) for column in _API_COLUMNS] for row in rows]
        self._client.insert("api_minutely", data, column_names=_API_COLUMNS)


class ClickHouseExecutor:
    """QueryExecutor implementation used by the API service."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(get_client(settings))

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = self._client.query(sql, parameters=params)
        return [
            dict(zip(result.column_names, row, strict=True)) for row in result.result_rows
        ]
