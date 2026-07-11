"""Seam: the typed retention query (issue #20, PRD §5.2).

Décision 2026-07-10: retention is identified-users-only — anonymous
cross-day retention is mathematically impossible by design (the daily
salt is destroyed). Same compilation discipline as the registry.
"""

import pytest
from pydantic import ValidationError

from oriflux.query.retention import RetentionRequest, build_retention

JULY = {"start": "2026-05-01T00:00:00Z", "end": "2026-07-01T00:00:00Z"}


def r(**overrides: object) -> RetentionRequest:
    payload: dict[str, object] = {
        "activation_event": "signup_completed",
        "granularity": "week",
        "period": JULY,
    }
    payload.update(overrides)
    return RetentionRequest.model_validate(payload)


class TestRetentionValidation:
    def test_activation_event_must_be_a_slug(self) -> None:
        with pytest.raises(ValidationError):
            r(activation_event="Not A Slug")

    def test_granularity_is_week_or_month(self) -> None:
        assert r(granularity="month").granularity == "month"
        with pytest.raises(ValidationError):
            r(granularity="day")


class TestRetentionSql:
    def test_cohorts_are_identified_only_and_targets_bound(self) -> None:
        sql, params = build_retention(r(), org_id="org-dev")
        assert "user_pseudo_id != ''" in sql
        assert "signup_completed" not in sql  # bound, never inlined
        assert "signup_completed" in params.values()
        assert params["org_id"] == "org-dev"

    def test_week_granularity_uses_monday_weeks(self) -> None:
        sql, _ = build_retention(r(), org_id="org-dev")
        assert "toStartOfWeek(toDateTime(timestamp), 1)" in sql
        assert "dateDiff('week'" in sql

    def test_month_granularity_uses_month_fragments(self) -> None:
        sql, _ = build_retention(r(granularity="month"), org_id="org-dev")
        assert "toStartOfMonth(toDateTime(timestamp))" in sql
        assert "dateDiff('month'" in sql

    def test_project_scoping_is_bound_when_given(self) -> None:
        sql, params = build_retention(r(project_id="proj-1"), org_id="org-dev")
        assert "project_id" in sql
        assert params["project_id"] == "proj-1"
