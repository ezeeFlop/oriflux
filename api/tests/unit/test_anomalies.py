"""Seam: seasonal anomaly detection (issue #27, PRD §5.5).

Pure statistics — a (weekday, hour) baseline over ~4 weeks of hourly
values, a robust deviation score, and a minimum-volume guard so
low-traffic projects stay quiet. No LLM here (explanations are phase 3).
"""

from datetime import UTC, datetime, timedelta

from oriflux.workers.anomalies import Baseline, score_deviation

NOW = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)  # a Wednesday, 15:00


def seasonal_history(weeks: int = 4) -> list[tuple[datetime, float]]:
    """Weekday-shaped traffic: 100/h on weekdays, 20/h weekends, ±0 noise."""
    rows = []
    start = NOW - timedelta(weeks=weeks)
    for hour in range(weeks * 7 * 24):
        ts = start + timedelta(hours=hour)
        value = 100.0 if ts.weekday() < 5 else 20.0
        rows.append((ts, value))
    return rows


class TestBaseline:
    def test_baseline_learns_the_weekly_shape(self) -> None:
        baseline = Baseline.fit(seasonal_history())
        assert baseline.expected(NOW) == 100.0  # Wednesday 15:00
        saturday = NOW + timedelta(days=3)
        assert baseline.expected(saturday) == 20.0

    def test_normal_traffic_is_not_anomalous(self) -> None:
        baseline = Baseline.fit(seasonal_history())
        assert score_deviation(105.0, baseline, NOW) is None

    def test_a_collapse_is_detected_with_a_readable_ratio(self) -> None:
        baseline = Baseline.fit(seasonal_history())
        detection = score_deviation(30.0, baseline, NOW)
        assert detection is not None
        assert detection.direction == "drop"
        assert detection.deviation_pct == -70.0

    def test_a_spike_is_detected(self) -> None:
        baseline = Baseline.fit(seasonal_history())
        detection = score_deviation(320.0, baseline, NOW)
        assert detection is not None
        assert detection.direction == "spike"

    def test_low_volume_projects_stay_quiet(self) -> None:
        tiny = [(ts, value / 50) for ts, value in seasonal_history()]  # 2/h weekdays
        baseline = Baseline.fit(tiny)
        assert score_deviation(0.0, baseline, NOW) is None  # 100% drop but ~2 events

    def test_empty_history_never_fires(self) -> None:
        baseline = Baseline.fit([])
        assert score_deviation(500.0, baseline, NOW) is None
