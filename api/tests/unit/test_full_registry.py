"""Seam: the grown query registry (issue #6) — the full §5.1 web-analytics
vocabulary behind the single typed query contract.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.query.registry import DIMENSIONS, METRICS

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}


def q(**overrides: object) -> QueryRequest:
    payload: dict[str, object] = {"metric": "pageviews", "period": JULY}
    payload.update(overrides)
    return QueryRequest.model_validate(payload)


class TestVocabulary:
    def test_all_standard_web_metrics_are_registered(self) -> None:
        assert {
            "pageviews", "visitors", "sessions", "bounce_rate", "session_duration",
        } <= set(METRICS)

    def test_all_standard_web_dimensions_are_registered(self) -> None:
        assert {
            "project_id", "country", "region", "city", "asn", "page", "referrer",
            "utm_source", "utm_medium", "utm_campaign", "device", "os", "browser",
            "locale", "traffic_class",
        } <= set(DIMENSIONS)

    def test_every_compatible_dimension_is_filterable_and_groupable(self) -> None:
        for metric_name, metric in METRICS.items():
            for dimension_name, dimension in DIMENSIONS.items():
                if metric.source not in dimension.sources:
                    continue
                request = q(
                    metric=metric_name,
                    dimensions=[dimension_name],
                    filters=[{"dimension": dimension_name, "op": "eq", "value": "x"}],
                )
                sql, params = build_query(request, org_id="o")
                assert "value" in sql

    def test_week_granularity_exists(self) -> None:
        sql, _ = build_query(q(granularity="week"), org_id="o")
        assert "toStartOfWeek" in sql


class TestHelpfulValidation:
    def test_unknown_metric_names_the_alternatives(self) -> None:
        with pytest.raises(ValidationError, match="visitors"):
            q(metric="uniques")

    def test_unknown_dimension_names_the_alternatives(self) -> None:
        with pytest.raises(ValidationError, match="utm_source"):
            q(dimensions=["utm"])

    def test_hour_granularity_is_capped_to_31_days(self) -> None:
        with pytest.raises(ValidationError, match="hour"):
            q(
                granularity="hour",
                period={"start": "2026-01-01T00:00:00Z", "end": "2026-03-15T00:00:00Z"},
            )

    def test_hour_granularity_within_31_days_is_fine(self) -> None:
        assert q(granularity="hour").granularity == "hour"


class TestCompareTo:
    def test_previous_year_is_accepted(self) -> None:
        assert q(compare_to="previous_year").compare_to == "previous_year"


class TestSqlShapes:
    def test_visitors_dedupe_by_visitor_hash(self) -> None:
        sql, _ = build_query(q(metric="visitors"), org_id="o")
        assert "uniq(visitor_hash)" in sql

    def test_session_metrics_aggregate_a_per_session_rollup(self) -> None:
        for metric in ("sessions", "bounce_rate", "session_duration"):
            sql, _ = build_query(q(metric=metric), org_id="o")
            assert "GROUP BY session_id" in sql, metric
            assert "session_id != ''" in sql, metric

    def test_session_metric_dimensions_come_from_the_rollup(self) -> None:
        sql, _ = build_query(
            q(metric="bounce_rate", dimensions=["country"], granularity="day"), org_id="o"
        )
        assert "any(country)" in sql
        assert "GROUP BY bucket, country" in sql

    def test_user_values_stay_parameterized_in_both_shapes(self) -> None:
        hostile = "x'; DROP TABLE events; --"
        for metric in ("pageviews", "sessions"):
            request = q(
                metric=metric,
                filters=[{"dimension": "page", "op": "eq", "value": hostile}],
            )
            sql, params = build_query(request, org_id="org-dev")
            assert hostile not in sql
            assert hostile in params.values()
            assert params["org_id"] == "org-dev"

    def test_period_bounds_are_parameterized(self) -> None:
        sql, params = build_query(q(), org_id="o")
        assert params["start"] == datetime(2026, 7, 1, tzinfo=UTC)
        assert "{start:DateTime64(3)}" in sql
