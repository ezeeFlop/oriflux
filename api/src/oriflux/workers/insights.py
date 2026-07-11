"""Insight detection (issue #35, PRD §6) — pure statistics, no LLM here.

A finding is a material week-over-week movement (or a from-zero signal)
on a watched metric; thresholds keep low-volume projects quiet, the same
philosophy as the anomaly job.
"""

from dataclasses import dataclass

MIN_DELTA_PCT = 25.0
MIN_VOLUME = 50.0


@dataclass(frozen=True)
class Finding:
    key: str  # idempotence key within (project, day)
    kind: str  # trend | new
    metric: str
    current: float
    previous: float
    delta_pct: float


def detect_findings(metrics: dict[str, tuple[float, float]]) -> list[Finding]:
    """metrics: name → (current period value, previous period value)."""
    findings: list[Finding] = []
    for metric, (current, previous) in metrics.items():
        if max(current, previous) < MIN_VOLUME:
            continue
        if previous == 0:
            findings.append(
                Finding(
                    key=f"new:{metric}", kind="new", metric=metric,
                    current=current, previous=0.0, delta_pct=100.0,
                )
            )
            continue
        delta_pct = round(100 * (current - previous) / previous, 1)
        if abs(delta_pct) < MIN_DELTA_PCT:
            continue
        findings.append(
            Finding(
                key=f"trend:{metric}", kind="trend", metric=metric,
                current=current, previous=previous, delta_pct=delta_pct,
            )
        )
    return findings
