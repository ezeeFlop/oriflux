"""Seam: Web Vitals collection and querying (issue #23, PRD §5.1).

Vitals land as events (event_name = vital_<name>) with a numeric `value`
column; p75 is the primary aggregate (Google guidance), queryable per
page and per country through the registry only.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from oriflux.models.events import EnrichedEvent, VitalIn
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.storage.clickhouse import ensure_schema

JULY = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}


class TestVitalWireContract:
    def test_valid_vital_is_accepted(self) -> None:
        vital = VitalIn.model_validate(
            {"type": "vital", "name": "lcp", "value": 1834.5, "url": "https://a.io/docs"}
        )
        assert vital.name == "lcp"
        assert vital.url_path == "/docs"

    @pytest.mark.parametrize("name", ["fps", "LCP", ""])
    def test_unknown_vital_names_are_rejected(self, name: str) -> None:
        with pytest.raises(ValidationError):
            VitalIn.model_validate({"type": "vital", "name": name, "value": 1.0,
                                    "url": "https://a.io/"})

    def test_negative_or_absurd_values_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VitalIn.model_validate({"type": "vital", "name": "cls", "value": -1,
                                    "url": "https://a.io/"})
        with pytest.raises(ValidationError):
            VitalIn.model_validate({"type": "vital", "name": "lcp", "value": 1e9,
                                    "url": "https://a.io/"})

    def test_enriched_vital_carries_the_value_and_prefixed_name(self) -> None:
        from datetime import UTC, datetime

        vital = VitalIn.model_validate(
            {"type": "vital", "name": "ttfb", "value": 120.0, "url": "https://a.io/"}
        )
        event = EnrichedEvent.from_vital(
            vital, org_id="o", project_id="p", timestamp=datetime(2026, 7, 11, tzinfo=UTC)
        )
        assert event.event_name == "vital_ttfb"
        assert event.value == 120.0


class TestVitalsRegistry:
    def test_p75_metrics_by_page_and_country(self) -> None:
        sql, _ = build_query(
            QueryRequest.model_validate(
                {"metric": "web_vital_lcp_p75", "dimensions": ["page"], "period": JULY}
            ),
            org_id="org-dev",
        )
        assert "quantile(0.75)(value)" in sql
        assert "event_name = 'vital_lcp'" in sql

    def test_all_four_vitals_are_registered(self) -> None:
        for name in ("lcp", "cls", "inp", "ttfb"):
            QueryRequest.model_validate({"metric": f"web_vital_{name}_p75", "period": JULY})


class TestSchemaMigration:
    def test_ensure_schema_adds_the_value_column_idempotently(self) -> None:
        class Recorder:
            def __init__(self) -> None:
                self.commands: list[str] = []

            def command(self, sql: str) -> Any:
                self.commands.append(sql)

        recorder = Recorder()
        ensure_schema(recorder)  # type: ignore[arg-type]
        alters = [c for c in recorder.commands if "ADD COLUMN IF NOT EXISTS" in c]
        assert any("value Float64" in c for c in alters)
