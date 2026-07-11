"""Seam: the typed query object — the single contract for dashboard, REST,
MCP and (later) Ask Oriflux.

PRD §8.3: one Pydantic query object (metric, dimensions, filters,
granularity, period, compare_to) validated against a hand-maintained
registry. Unknown metrics/dimensions must die at schema validation, and no
user value may ever be interpolated into SQL text.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}


def q(**overrides: object) -> QueryRequest:
    payload: dict[str, object] = {"metric": "pageviews", "period": JULY}
    payload.update(overrides)
    return QueryRequest.model_validate(payload)


class TestSchemaValidation:
    def test_pageviews_is_a_known_metric(self) -> None:
        assert q().metric == "pageviews"

    def test_unknown_metric_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown metric"):
            q(metric="revenue")

    def test_unknown_dimension_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown dimension"):
            q(dimensions=["favorite_color"])

    def test_filter_on_unknown_dimension_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown dimension"):
            q(filters=[{"dimension": "favorite_color", "op": "eq", "value": "blue"}])

    def test_period_must_be_ordered(self) -> None:
        with pytest.raises(ValidationError, match="period"):
            q(period={"start": "2026-08-01T00:00:00Z", "end": "2026-07-01T00:00:00Z"})

    def test_known_dimension_and_filter_are_accepted(self) -> None:
        request = q(
            dimensions=["country"],
            filters=[{"dimension": "project_id", "op": "eq", "value": "proj-dev"}],
            granularity="day",
        )
        assert request.dimensions == ["country"]

    def test_period_is_parsed_to_utc_datetimes(self) -> None:
        assert q().period.start == datetime(2026, 7, 1, tzinfo=UTC)


class TestSqlSafety:
    def test_user_values_are_bound_as_parameters_never_inlined(self) -> None:
        hostile = "x'; DROP TABLE events; --"
        request = q(filters=[{"dimension": "project_id", "op": "eq", "value": hostile}])
        sql, params = build_query(request, org_id="org-dev")
        assert hostile not in sql
        assert hostile in params.values()

    def test_org_scoping_is_always_applied(self) -> None:
        sql, params = build_query(q(), org_id="org-dev")
        assert "org_id" in sql
        assert params["org_id"] == "org-dev"

    def test_grouping_follows_requested_dimensions_and_granularity(self) -> None:
        sql, _ = build_query(q(dimensions=["country"], granularity="day"), org_id="o")
        assert "GROUP BY" in sql
        assert "country" in sql


class TestCustomEventsRegistry:
    """§5.2 / issue #17: custom events queryable through the registry only."""

    def test_custom_events_by_event_name(self) -> None:
        sql, _ = build_query(
            q(metric="custom_events", dimensions=["event_name"]), org_id="org-dev"
        )
        assert "event_name != 'pageview'" in sql
        assert "GROUP BY event_name" in sql

    def test_custom_events_never_count_pageviews(self) -> None:
        sql, _ = build_query(q(metric="custom_events"), org_id="org-dev")
        assert "event_name != 'pageview'" in sql

    def test_event_name_dimension_rejected_on_api_metrics(self) -> None:
        with pytest.raises(ValidationError):
            q(metric="api_requests", dimensions=["event_name"])

    def test_custom_events_filterable_by_event_name(self) -> None:
        sql, params = build_query(
            q(
                metric="custom_events",
                filters=[{"dimension": "event_name", "op": "eq", "value": "signup_completed"}],
            ),
            org_id="org-dev",
        )
        assert "signup_completed" not in sql  # bound, never inlined
        assert "signup_completed" in params.values()
