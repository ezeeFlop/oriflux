"""Issue #8 e2e: SDK-shaped payload → ingest → batcher → api_minutely →
registry percentiles correct against a known workload."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from tests.integration.conftest import API_URL, INGEST_URL, Tenant

pytestmark = pytest.mark.integration

# Known workload: 100 requests on one endpoint, 5 of them 5xx.
# Latency values 10 ms ×50, 100 ms ×45, 1000 ms ×5 (cumulative 50/95/100)
# → p50 = 10, p95 = 100, p99 = 1000, error_rate_5xx = 5 %.
WORKLOAD = {
    "window_start": datetime.now(tz=UTC).isoformat(),
    "overflow_count": 0,
    "entries": [
        {
            "endpoint": "/known/{id}", "method": "GET", "status_code": 200,
            "consumer": "acme", "ip": "81.2.69.142", "count": 95,
            "bytes_in": 950, "bytes_out": 9500,
            "latency_ms": {"10": 50, "100": 45}, "overflow": False,
        },
        {
            "endpoint": "/known/{id}", "method": "GET", "status_code": 500,
            "consumer": "acme", "ip": "81.2.69.142", "count": 5,
            "bytes_in": 50, "bytes_out": 100,
            "latency_ms": {"1000": 5}, "overflow": False,
        },
    ],
}


def query(read_key: str, **payload: Any) -> list[dict[str, Any]]:
    now = datetime.now(tz=UTC)
    payload.setdefault(
        "period",
        {"start": (now - timedelta(days=1)).isoformat(),
         "end": (now + timedelta(days=1)).isoformat()},
    )
    response = httpx.post(
        f"{API_URL}/api/v1/query",
        json=payload,
        headers={"Authorization": f"Bearer {read_key}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["results"]


class TestKnownWorkload:
    def test_percentiles_and_error_rate_match_the_workload(self, tenant: Tenant) -> None:
        posted = httpx.post(
            f"{INGEST_URL}/api/v1/api-metrics",
            json=WORKLOAD,
            headers={"Authorization": f"Bearer {tenant.ingest_key}"},
            timeout=5,
        )
        assert posted.status_code == 202, posted.text

        deadline = time.monotonic() + 10.0
        while True:
            results = query(tenant.read_key, metric="api_requests")
            if results and results[0]["value"] == 100:
                break
            if time.monotonic() > deadline:
                pytest.fail(f"api_minutely rows never arrived (last: {results})")
            time.sleep(0.25)

        assert query(tenant.read_key, metric="api_error_rate_5xx")[0]["value"] == 5.0
        assert query(tenant.read_key, metric="api_latency_p50")[0]["value"] == 10.0
        assert query(tenant.read_key, metric="api_latency_p95")[0]["value"] == 100.0
        assert query(tenant.read_key, metric="api_latency_p99")[0]["value"] == 1000.0

        by_endpoint = query(
            tenant.read_key, metric="api_latency_p95", dimensions=["endpoint"]
        )
        assert by_endpoint == [{"endpoint": "/known/{id}", "value": 100.0}]

        by_country = {
            r["country"]: r["value"]
            for r in query(tenant.read_key, metric="api_requests", dimensions=["country"])
        }
        assert by_country == {"GB": 100} or by_country == {"": 100}  # GB when geoip mounted
