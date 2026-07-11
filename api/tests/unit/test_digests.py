"""Seam: scheduled email digests (issue #26, PRD §5.5).

Numbers-first in phase 2 (the AI narrative is phase 3): per-project
visitors/pageviews/API health with week-over-week deltas, rendered in the
subscriber's language, sent once per period (idempotent), via Resend.
"""

from datetime import UTC, datetime

from oriflux.workers.digests import due_period, render_digest

MONDAY = datetime(2026, 7, 6, 6, 30, tzinfo=UTC)
TUESDAY = datetime(2026, 7, 7, 6, 30, tzinfo=UTC)
FIRST = datetime(2026, 7, 1, 6, 30, tzinfo=UTC)

NUMBERS = [
    {
        "project": "AudiGEO",
        "visitors": 420, "visitors_prev": 380,
        "pageviews": 1300, "pageviews_prev": 1250,
        "api_requests": 52000, "api_requests_prev": 61000,
        "error_rate_5xx": 0.2,
    }
]


class TestDuePeriod:
    def test_weekly_digest_is_due_on_monday_with_a_stable_key(self) -> None:
        assert due_period("weekly", MONDAY) == "2026-W27"  # the week that just ended
        assert due_period("weekly", TUESDAY) is None

    def test_monthly_digest_is_due_on_the_first(self) -> None:
        assert due_period("monthly", FIRST) == "2026-06"  # covers the previous month
        assert due_period("monthly", TUESDAY) is None


class TestRenderDigest:
    def test_renders_in_the_subscriber_language(self) -> None:
        subject_fr, body_fr = render_digest(NUMBERS, language="fr", period_label="S28")
        subject_en, body_en = render_digest(NUMBERS, language="en", period_label="W28")
        subject_es, body_es = render_digest(NUMBERS, language="es", period_label="S28")
        assert "Visiteurs" in body_fr
        assert "Visitors" in body_en
        assert "Visitantes" in body_es
        assert "AudiGEO" in body_fr
        assert subject_fr != subject_en != subject_es

    def test_deltas_are_signed_percentages(self) -> None:
        _, body = render_digest(NUMBERS, language="en", period_label="W28")
        assert "+10.5%" in body  # visitors 380 → 420
        assert "-14.8%" in body  # api requests 61000 → 52000

    def test_numbers_only_no_placeholder_inventions(self) -> None:
        _, body = render_digest([], language="en", period_label="W28")
        assert "no data" in body.lower()
