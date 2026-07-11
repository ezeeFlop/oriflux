"""Seam: the wire contract for collected events (what SDKs POST to ingest).

The ingest endpoint validates payloads with Pydantic before anything else
happens; these tests pin down what is accepted and what is rejected.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from oriflux.models.events import CustomEventIn, EnrichedEvent, IdentifyIn, PageviewIn


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


class TestCustomEventWireContract:
    """§5.2: oriflux.track(name, props) — issue #17."""

    def test_valid_custom_event_is_accepted(self) -> None:
        event = CustomEventIn.model_validate(
            {"type": "event", "name": "signup_completed", "url": "https://a.io/join",
             "props": {"plan": "pro"}}
        )
        assert event.name == "signup_completed"
        assert event.url_path == "/join"

    def test_url_is_optional_for_custom_events(self) -> None:
        event = CustomEventIn.model_validate({"type": "event", "name": "job_done"})
        assert event.url_path == ""

    @pytest.mark.parametrize("name", ["", "Signup", "9lives", "a b", "a" * 65, "é_vent"])
    def test_non_slug_names_are_rejected(self, name: str) -> None:
        with pytest.raises(ValidationError):
            CustomEventIn.model_validate({"type": "event", "name": name})

    def test_pageview_is_not_a_valid_custom_event_name(self) -> None:
        # would corrupt every pageview metric in the registry
        with pytest.raises(ValidationError):
            CustomEventIn.model_validate({"type": "event", "name": "pageview"})

    def test_oversized_props_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="props"):
            CustomEventIn.model_validate(
                {"type": "event", "name": "big", "props": {"blob": "x" * 5000}}
            )

    def test_too_many_prop_keys_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="props"):
            CustomEventIn.model_validate(
                {"type": "event", "name": "wide", "props": {f"k{i}": i for i in range(40)}}
            )


class TestIdentifyWireContract:
    """§5.2 + §9: identify() accepts only pseudonymous IDs — PII dies at
    validation with a message naming the reason (issue #17)."""

    def test_pseudonymous_id_is_accepted(self) -> None:
        identify = IdentifyIn.model_validate({"type": "identify", "user_id": "usr_8f3a2c"})
        assert identify.user_id == "usr_8f3a2c"

    def test_email_shaped_user_id_is_rejected_naming_the_reason(self) -> None:
        with pytest.raises(ValidationError, match="email"):
            IdentifyIn.model_validate({"type": "identify", "user_id": "jane@corp.io"})

    def test_phone_shaped_user_id_is_rejected_naming_the_reason(self) -> None:
        with pytest.raises(ValidationError, match="phone"):
            IdentifyIn.model_validate({"type": "identify", "user_id": "+33612345678"})

    def test_email_shaped_trait_value_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="email"):
            IdentifyIn.model_validate(
                {"type": "identify", "user_id": "usr_1", "traits": {"contact": "j@x.io"}}
            )

    def test_plain_traits_are_accepted(self) -> None:
        identify = IdentifyIn.model_validate(
            {"type": "identify", "user_id": "usr_1", "traits": {"plan": "pro", "tenant": "acme"}}
        )
        assert identify.traits == {"plan": "pro", "tenant": "acme"}

    def test_overlong_user_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IdentifyIn.model_validate({"type": "identify", "user_id": "u" * 200})
