"""Hard gate (PRD #75 / #76): every metric and dimension in the query registry
MUST have a glossary definition in ALL three UI locales. The registry is the
single source of truth for what terms exist; this test guarantees the in-app
glossary never drifts or ships incomplete. If it fails, add the missing
`glossary.<name>.short` entry to web/src/i18n/{fr,en,es}.json.
"""

import json
from pathlib import Path

import pytest

from oriflux.query.registry import DIMENSIONS, METRICS

_I18N_DIR = Path(__file__).resolve().parents[3] / "web" / "src" / "i18n"
_LOCALES = ("fr", "en", "es")

# Registry terms that are internal plumbing, not user-facing analytics concepts,
# so they need no glossary entry. Keep this list tiny and justified.
_EXEMPT: frozenset[str] = frozenset({"project_id"})

_TERMS = sorted((set(DIMENSIONS) | set(METRICS)) - _EXEMPT)


def _load(locale: str) -> dict:
    return json.loads((_I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def _short(bundle: dict, term: str) -> str | None:
    entry = bundle.get("glossary", {}).get(term)
    if not isinstance(entry, dict):
        return None
    value = entry.get("short")
    return value if isinstance(value, str) and value.strip() else None


@pytest.mark.parametrize("locale", _LOCALES)
def test_every_registry_term_has_a_glossary_short_in_locale(locale: str) -> None:
    bundle = _load(locale)
    missing = [term for term in _TERMS if _short(bundle, term) is None]
    assert not missing, (
        f"[{locale}] glossary.<term>.short missing/empty for: {missing}. "
        f"Add them to web/src/i18n/{locale}.json."
    )


def test_locales_cover_exactly_the_same_glossary_terms() -> None:
    """No locale may define a glossary term the others don't (catches typos /
    orphaned entries across FR/EN/ES)."""
    per_locale = {loc: set(_load(loc).get("glossary", {})) for loc in _LOCALES}
    fr, en, es = (per_locale["fr"], per_locale["en"], per_locale["es"])
    assert fr == en == es, (
        "glossary term sets differ across locales: "
        f"only in fr={fr - en - es}, only in en={en - fr - es}, only in es={es - fr - en}"
    )
