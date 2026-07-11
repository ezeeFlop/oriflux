"""Scheduled email digests (issue #26, PRD §5.5) — numbers only.

Weekly digests go out on Mondays (covering the previous ISO week),
monthly ones on the 1st (covering the previous month); `due_period`
returns a stable idempotence key or None. Rendering is a pure function
in the subscriber's language (FR/EN/ES); the AI narrative is phase 3.
"""

from datetime import UTC, datetime, timedelta

_STRINGS: dict[str, dict[str, str]] = {
    "fr": {
        "subject": "Oriflux — digest {period}",
        "heading": "Votre digest Oriflux — {period}",
        "visitors": "Visiteurs",
        "pageviews": "Pages vues",
        "api": "Requêtes API",
        "errors": "Taux 5xx",
        "empty": "Aucune donnée sur la période.",
        "footer": "Gérez vos digests dans le dashboard Oriflux.",
    },
    "en": {
        "subject": "Oriflux — {period} digest",
        "heading": "Your Oriflux digest — {period}",
        "visitors": "Visitors",
        "pageviews": "Pageviews",
        "api": "API requests",
        "errors": "5xx rate",
        "empty": "No data for this period.",
        "footer": "Manage your digests in the Oriflux dashboard.",
    },
    "es": {
        "subject": "Oriflux — resumen {period}",
        "heading": "Su resumen Oriflux — {period}",
        "visitors": "Visitantes",
        "pageviews": "Páginas vistas",
        "api": "Peticiones API",
        "errors": "Tasa 5xx",
        "empty": "Sin datos para este período.",
        "footer": "Gestione sus resúmenes en el panel de Oriflux.",
    },
}


def due_period(cadence: str, now: datetime) -> str | None:
    """Idempotence key when a digest is due right now, else None."""
    if cadence == "weekly":
        if now.weekday() != 0:  # Monday
            return None
        year, week, _ = (now - timedelta(days=1)).isocalendar()  # the week just ended
        return f"{year}-W{week:02d}"
    if cadence == "monthly":
        if now.day != 1:
            return None
        previous = (now.replace(day=1) - timedelta(days=1)).astimezone(UTC)
        return f"{previous.year}-{previous.month:02d}"
    return None


def _delta(current: float, previous: float) -> str:
    if previous <= 0:
        return ""
    pct = 100 * (current - previous) / previous
    return f" ({'+' if pct >= 0 else ''}{pct:.1f}%)"


def render_digest(
    numbers: list[dict[str, object]], *, language: str, period_label: str,
    narrative: str = "",
) -> tuple[str, str]:
    """→ (subject, plain-text body). Numbers only — the optional narrative
    (issue #37) is generated FROM these numbers and prepended, never a
    replacement for them."""
    strings = _STRINGS.get(language, _STRINGS["en"])
    subject = strings["subject"].format(period=period_label)
    lines = [strings["heading"].format(period=period_label), ""]
    if narrative:
        lines.extend([narrative.strip(), ""])
    if not numbers:
        lines.append(strings["empty"])
    for row in numbers:
        lines.append(f"■ {row['project']}")
        lines.append(
            f"  {strings['visitors']}: {row['visitors']}"
            f"{_delta(float(row['visitors']), float(row['visitors_prev']))}"  # type: ignore[arg-type]
        )
        lines.append(
            f"  {strings['pageviews']}: {row['pageviews']}"
            f"{_delta(float(row['pageviews']), float(row['pageviews_prev']))}"  # type: ignore[arg-type]
        )
        lines.append(
            f"  {strings['api']}: {row['api_requests']}"
            f"{_delta(float(row['api_requests']), float(row['api_requests_prev']))}"  # type: ignore[arg-type]
        )
        lines.append(f"  {strings['errors']}: {row['error_rate_5xx']}%")
        lines.append("")
    lines.append(strings["footer"])
    return subject, "\n".join(lines)
