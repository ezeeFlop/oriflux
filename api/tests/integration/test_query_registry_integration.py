"""Issue #6 integration: registry↔ClickHouse drift, metric correctness on a
crafted fixture, and the NFR §11 latency budget on a seeded 13-month set.
"""

import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from oriflux.config import Settings
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.query.registry import DIMENSIONS, GRANULARITY_SQL, METRICS
from oriflux.storage.clickhouse import ClickHouseExecutor, get_client

pytestmark = pytest.mark.integration

NOW = datetime.now(tz=UTC)


def wide(days_back: int = 30) -> dict[str, Any]:
    return {"start": (NOW - timedelta(days=days_back)).isoformat(),
            "end": (NOW + timedelta(days=1)).isoformat()}


def run(executor: ClickHouseExecutor, org_id: str, **payload: Any) -> list[dict[str, Any]]:
    payload.setdefault("period", wide())
    request = QueryRequest.model_validate(payload)
    sql, params = build_query(request, org_id=org_id)
    return executor.execute(sql, params)


@pytest.fixture(scope="module")
def executor(settings: Settings) -> ClickHouseExecutor:
    return ClickHouseExecutor(get_client(settings))


class TestRegistryDrift:
    """Every registry entry must execute against the real schema — a renamed
    column or a typo'd fragment fails here, not in production."""

    def test_every_metric_executes(self, executor: ClickHouseExecutor) -> None:
        for metric in METRICS:
            run(executor, "drift-org", metric=metric)

    def test_every_metric_dimension_combination_executes(
        self, executor: ClickHouseExecutor
    ) -> None:
        for metric_name, metric in METRICS.items():
            for dimension_name, dimension in DIMENSIONS.items():
                if metric.source not in dimension.sources:
                    continue
                run(
                    executor, "drift-org", metric=metric_name, dimensions=[dimension_name],
                    filters=[{"dimension": dimension_name, "op": "eq", "value": "1"}],
                )

    def test_every_granularity_executes_for_every_metric(
        self, executor: ClickHouseExecutor
    ) -> None:
        for metric in METRICS:
            for granularity in GRANULARITY_SQL:
                run(executor, "drift-org", metric=metric, granularity=granularity)


def _row(org: str, ts: datetime, visitor: str, session: str, path: str) -> dict[str, Any]:
    return {
        "event_id": uuid.uuid4(), "timestamp": ts, "org_id": org, "project_id": "p",
        "source_type": "web", "event_name": "pageview", "visitor_hash": visitor,
        "session_id": session, "user_pseudo_id": "", "tenant_id": "", "url_path": path,
        "referrer": "", "utm_source": "", "utm_medium": "", "utm_campaign": "",
        "utm_term": "", "utm_content": "", "country": "FR", "region": "", "city": "",
        "asn": 0, "device": "", "os": "", "browser": "", "locale": "",
        "traffic_class": "human", "props": "{}",
    }


def _insert(settings: Settings, rows: list[dict[str, Any]]) -> None:
    client = get_client(settings)
    columns = list(rows[0].keys())
    client.insert("events", [[r[c] for c in columns] for r in rows], column_names=columns)


class TestMetricCorrectness:
    def test_visitors_sessions_bounce_and_duration(
        self, settings: Settings, executor: ClickHouseExecutor
    ) -> None:
        """Visitor A: one session of 2 pageviews 10 min apart. Visitor B: one
        bounced pageview. → visitors 2, pageviews 3, sessions 2,
        bounce_rate 50 %, avg duration (600+0)/2 = 300 s."""
        org = f"correct-{uuid.uuid4().hex[:8]}"
        t0 = NOW - timedelta(hours=2)
        _insert(settings, [
            _row(org, t0, "vis-a", "sess-a", "/one"),
            _row(org, t0 + timedelta(minutes=10), "vis-a", "sess-a", "/two"),
            _row(org, t0 + timedelta(minutes=5), "vis-b", "sess-b", "/one"),
        ])

        assert run(executor, org, metric="pageviews")[0]["value"] == 3
        assert run(executor, org, metric="visitors")[0]["value"] == 2
        assert run(executor, org, metric="sessions")[0]["value"] == 2
        assert run(executor, org, metric="bounce_rate")[0]["value"] == 50.0
        assert run(executor, org, metric="session_duration")[0]["value"] == 300.0

    def test_dimensional_breakdown(self, settings: Settings, executor: ClickHouseExecutor) -> None:
        org = f"correct-{uuid.uuid4().hex[:8]}"
        t0 = NOW - timedelta(hours=1)
        rows = [_row(org, t0, f"v{i}", f"s{i}", "/x") for i in range(3)]
        rows[2]["country"] = "DE"
        _insert(settings, rows)

        by_country = {
            r["country"]: r["value"]
            for r in run(executor, org, metric="pageviews", dimensions=["country"])
        }
        assert by_country == {"FR": 2, "DE": 1}


PERF_ORG = "perf-seed-v1"
PERF_TARGET_ROWS = 1_200_000


def _seed_perf_dataset(settings: Settings) -> None:
    client = get_client(settings)
    existing = client.query(
        "SELECT count() FROM events WHERE org_id = {o:String}", parameters={"o": PERF_ORG}
    ).result_rows[0][0]
    if existing >= PERF_TARGET_ROWS:
        return
    rng = random.Random(42)
    countries = ["FR", "DE", "US", "ES", "GB", "IT", "NL", "BE", "CA", "CH"]
    pages = [f"/page-{i}" for i in range(50)]
    browsers = ["Chrome", "Firefox", "Safari", "Edge"]
    batch: list[dict[str, Any]] = []
    remaining = PERF_TARGET_ROWS - existing
    for i in range(remaining):
        day_offset = rng.betavariate(1.2, 3.0) * 395  # denser near "now", 13 months back
        ts = NOW - timedelta(days=day_offset, seconds=rng.randint(0, 86_399))
        visitor = f"v-{ts.date()}-{rng.randint(0, 4000)}"
        row = _row(PERF_ORG, ts, visitor, f"s-{visitor}-{rng.randint(0, 2)}",
                   rng.choice(pages))
        row["country"] = rng.choice(countries)
        row["browser"] = rng.choice(browsers)
        batch.append(row)
        if len(batch) >= 100_000:
            _insert(settings, batch)
            batch = []
    if batch:
        _insert(settings, batch)


class TestLatencyBudget:
    def test_p95_of_dashboard_queries_under_500ms_on_13_months(
        self, settings: Settings, executor: ClickHouseExecutor
    ) -> None:
        """NFR §11: dashboard queries < 500 ms (p95) over 13 months of data."""
        _seed_perf_dataset(settings)

        dashboard_queries: list[dict[str, Any]] = [
            {"metric": "pageviews", "granularity": "day", "period": wide(30)},
            {"metric": "visitors", "dimensions": ["country"], "period": wide(30)},
            {"metric": "sessions", "granularity": "day", "period": wide(30)},
            {"metric": "bounce_rate", "period": wide(30)},
            {"metric": "visitors", "dimensions": ["page"], "period": wide(30)},
            {"metric": "pageviews", "granularity": "month", "period": wide(395)},
        ]
        latencies: list[float] = []
        for payload in dashboard_queries:
            for _ in range(10):
                started = time.monotonic()
                run(executor, PERF_ORG, **payload)
                latencies.append(time.monotonic() - started)
        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        assert p95 < 0.5, f"p95 {p95 * 1000:.0f} ms over budget (median {latencies[len(latencies) // 2] * 1000:.0f} ms)"
