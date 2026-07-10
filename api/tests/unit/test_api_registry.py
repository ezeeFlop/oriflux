"""Seam: API-analytics metrics in the registry (issue #8, §5.3)."""

import pytest
from pydantic import ValidationError

from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.query.registry import DIMENSIONS, METRICS

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}


def q(**overrides: object) -> QueryRequest:
    payload: dict[str, object] = {"metric": "api_requests", "period": JULY}
    payload.update(overrides)
    return QueryRequest.model_validate(payload)


class TestApiVocabulary:
    def test_api_metrics_are_registered(self) -> None:
        assert {
            "api_requests", "api_error_rate_4xx", "api_error_rate_5xx",
            "api_latency_p50", "api_latency_p95", "api_latency_p99",
        } <= set(METRICS)

    def test_api_dimensions_are_registered(self) -> None:
        assert {"endpoint", "method", "status_class", "consumer"} <= set(DIMENSIONS)


class TestSourceCompatibility:
    def test_web_only_dimensions_are_rejected_for_api_metrics(self) -> None:
        with pytest.raises(ValidationError, match="endpoint"):  # message lists valid dims
            q(dimensions=["page"])

    def test_api_only_dimensions_are_rejected_for_web_metrics(self) -> None:
        with pytest.raises(ValidationError, match="country"):
            q(metric="pageviews", dimensions=["endpoint"])

    def test_filters_follow_the_same_compatibility(self) -> None:
        with pytest.raises(ValidationError, match="not available for metric"):
            q(filters=[{"dimension": "browser", "op": "eq", "value": "Chrome"}])

    def test_shared_dimensions_work_on_both_sources(self) -> None:
        for metric in ("pageviews", "api_requests"):
            request = q(metric=metric, dimensions=["country"], granularity="day")
            sql, _ = build_query(request, org_id="o")
            assert "country" in sql


class TestApiSqlShapes:
    def test_api_metrics_read_api_minutely(self) -> None:
        sql, _ = build_query(q(), org_id="o")
        assert "FROM api_minutely FINAL" in sql
        assert "sum(count)" in sql
        assert "timestamp_min" in sql

    def test_latency_percentiles_use_weighted_quantiles_over_the_buckets(self) -> None:
        sql, _ = build_query(q(metric="api_latency_p95", dimensions=["endpoint"]), org_id="o")
        assert "ARRAY JOIN latency_bucket_ms AS lat_ms, latency_counts AS lat_cnt" in sql
        assert "quantileExactWeighted(0.95)(lat_ms, lat_cnt)" in sql
        assert "GROUP BY endpoint" in sql

    def test_error_rates_split_by_status_class(self) -> None:
        sql, _ = build_query(q(metric="api_error_rate_5xx"), org_id="o")
        assert "status_class = '5xx'" in sql

    def test_org_scoping_and_parameterization_hold(self) -> None:
        hostile = "x'; DROP TABLE api_minutely; --"
        request = q(filters=[{"dimension": "endpoint", "op": "eq", "value": hostile}])
        sql, params = build_query(request, org_id="org-a")
        assert hostile not in sql
        assert params["org_id"] == "org-a"
