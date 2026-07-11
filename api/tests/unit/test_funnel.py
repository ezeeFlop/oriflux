"""Seam: the typed funnel query (issue #19, PRD §5.2).

Décision 2026-07-10: multi-day funnels are identified-only; anonymous
funnels are session-scoped (the daily salt makes cross-day anonymous
sequences impossible by design). Compilation follows the registry
discipline — vetted fragments only, user values always bound.
"""

import pytest
from pydantic import ValidationError

from oriflux.query.funnel import FunnelRequest, build_funnel

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}


def f(**overrides: object) -> FunnelRequest:
    payload: dict[str, object] = {
        "steps": [
            {"kind": "page", "target": "/pricing"},
            {"kind": "event", "target": "signup_completed"},
        ],
        "scope": "session",
        "period": JULY,
    }
    payload.update(overrides)
    return FunnelRequest.model_validate(payload)


class TestFunnelValidation:
    def test_two_to_eight_steps(self) -> None:
        with pytest.raises(ValidationError):
            f(steps=[{"kind": "page", "target": "/only-one"}])
        with pytest.raises(ValidationError):
            f(steps=[{"kind": "page", "target": f"/s{i}"} for i in range(9)])

    def test_step_targets_follow_goal_rules(self) -> None:
        with pytest.raises(ValidationError):
            f(steps=[{"kind": "event", "target": "Not A Slug"},
                     {"kind": "page", "target": "/ok"}])
        with pytest.raises(ValidationError):
            f(steps=[{"kind": "page", "target": "no-slash"},
                     {"kind": "page", "target": "/ok"}])

    def test_session_scope_caps_the_window_at_a_day(self) -> None:
        assert f(window_hours=6).window_hours == 6
        with pytest.raises(ValidationError, match="session"):
            f(window_hours=48)

    def test_identified_scope_allows_multi_day_windows(self) -> None:
        request = f(scope="identified", window_hours=7 * 24)
        assert request.window_hours == 168
        with pytest.raises(ValidationError):
            f(scope="identified", window_hours=31 * 24)

    def test_segment_must_be_a_registry_events_dimension(self) -> None:
        assert f(segment_by="country").segment_by == "country"
        with pytest.raises(ValidationError):
            f(segment_by="endpoint")  # api-only dimension
        with pytest.raises(ValidationError):
            f(segment_by="favorite_color")


class TestFunnelSql:
    def test_session_scope_groups_by_session_and_binds_targets(self) -> None:
        sql, params = build_funnel(f(), org_id="org-dev")
        assert "windowFunnel" in sql
        # CH 24.8 rejects DateTime64 in windowFunnel — the fragment must cast
        assert "toDateTime(timestamp)" in sql
        assert "session_id" in sql
        assert "/pricing" not in sql and "signup_completed" not in sql
        assert "/pricing" in params.values()
        assert "signup_completed" in params.values()
        assert params["org_id"] == "org-dev"

    def test_identified_scope_groups_by_user_pseudo_id_excluding_anonymous(self) -> None:
        sql, _ = build_funnel(f(scope="identified"), org_id="org-dev")
        assert "user_pseudo_id" in sql
        assert "user_pseudo_id != ''" in sql

    def test_segment_dimension_uses_the_registry_fragment(self) -> None:
        sql, _ = build_funnel(f(segment_by="country"), org_id="org-dev")
        assert "country" in sql
        assert "GROUP BY" in sql
