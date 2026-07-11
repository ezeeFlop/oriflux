"""Seasonal anomaly detection (issue #27, PRD §5.5) — pure statistics.

Baseline = per-(weekday, hour) mean/σ over ~4 weeks of hourly values;
a deviation fires when the current hour sits ≥ 3 robust σ away AND the
volumes involved clear a floor — low-traffic projects must stay quiet
(false-positive guard, documented on the issue). The LLM explanation
layer is phase 3 (§6 « anomalies expliquées »).
"""

import statistics
from dataclasses import dataclass
from datetime import datetime

MIN_VOLUME = 50.0  # events/hour: below this, deviations are noise
Z_THRESHOLD = 3.0
MIN_DEVIATION_PCT = 40.0  # a 3σ blip that moves < 40% is not worth waking anyone


@dataclass(frozen=True)
class Detection:
    direction: str  # "drop" | "spike"
    expected: float
    observed: float
    deviation_pct: float  # signed, relative to expected


@dataclass(frozen=True)
class Baseline:
    buckets: dict[tuple[int, int], tuple[float, float]]  # (weekday, hour) → (mean, σ)

    @classmethod
    def fit(cls, history: list[tuple[datetime, float]]) -> "Baseline":
        grouped: dict[tuple[int, int], list[float]] = {}
        for ts, value in history:
            grouped.setdefault((ts.weekday(), ts.hour), []).append(value)
        buckets = {
            key: (
                statistics.fmean(values),
                statistics.pstdev(values) if len(values) > 1 else 0.0,
            )
            for key, values in grouped.items()
            if values
        }
        return cls(buckets=buckets)

    def expected(self, moment: datetime) -> float | None:
        bucket = self.buckets.get((moment.weekday(), moment.hour))
        return bucket[0] if bucket else None

    def sigma(self, moment: datetime) -> float:
        bucket = self.buckets.get((moment.weekday(), moment.hour))
        return bucket[1] if bucket else 0.0


def score_deviation(
    observed: float, baseline: Baseline, moment: datetime
) -> Detection | None:
    expected = baseline.expected(moment)
    if expected is None:
        return None
    if max(observed, expected) < MIN_VOLUME:
        return None  # too small to mean anything
    # robust σ floor: 10% of expected (flat seasonal series have σ ≈ 0)
    sigma = max(baseline.sigma(moment), expected * 0.1, 1.0)
    z = (observed - expected) / sigma
    deviation_pct = round(100 * (observed - expected) / expected, 1) if expected else 0.0
    if abs(z) < Z_THRESHOLD or abs(deviation_pct) < MIN_DEVIATION_PCT:
        return None
    return Detection(
        direction="drop" if observed < expected else "spike",
        expected=round(expected, 1),
        observed=round(observed, 1),
        deviation_pct=deviation_pct,
    )
