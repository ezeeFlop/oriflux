"""Seam: the wire contract for collected events (what SDKs POST to ingest).

The ingest endpoint validates payloads with Pydantic before anything else
happens; these tests pin down what is accepted and what is rejected.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from oriflux.models.events import EnrichedEvent, PageviewIn


class TestPageviewWireContract:
    def test_valid_pageview_is_accepted(self) -> None:
        event = PageviewIn.model_validate(
            {"type": "pageview", "url": "https://sponge-theory.ai/pricing?utm_source=x"}
        )
        assert event.type == "pageview"
        assert event.url_path == "/pricing"

    def test_url_is_required(self) -> None:
        with pytest.raises(ValidationError):
            PageviewIn.model_validate({"type": "pageview"})

    def test_non_http_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PageviewIn.model_validate({"type": "pageview", "url": "not a url"})

    def test_unknown_event_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PageviewIn.model_validate({"type": "identify", "url": "https://a.io/"})

    def test_referrer_defaults_to_empty(self) -> None:
        event = PageviewIn.model_validate({"type": "pageview", "url": "https://a.io/"})
        assert event.referrer == ""


class TestEnrichment:
    def test_enriched_event_gets_a_uuid_and_keeps_traffic_class_unclassified(self) -> None:
        wire = PageviewIn.model_validate({"type": "pageview", "url": "https://a.io/docs"})
        event = EnrichedEvent.from_pageview(
            wire,
            org_id="org-dev",
            project_id="proj-dev",
            timestamp=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        )
        assert isinstance(event.event_id, UUID)
        assert event.event_name == "pageview"
        assert event.source_type == "web"
        assert event.url_path == "/docs"
        # column exists from the very first event, but nothing classifies yet (issue #4)
        assert event.traffic_class == ""

    def test_two_enrichments_of_the_same_payload_get_distinct_uuids(self) -> None:
        wire = PageviewIn.model_validate({"type": "pageview", "url": "https://a.io/"})
        ts = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
        a = EnrichedEvent.from_pageview(wire, org_id="o", project_id="p", timestamp=ts)
        b = EnrichedEvent.from_pageview(wire, org_id="o", project_id="p", timestamp=ts)
        assert a.event_id != b.event_id
