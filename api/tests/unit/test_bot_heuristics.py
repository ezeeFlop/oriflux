"""Seam: behavioral bot heuristics on top of UA rules (issue #21, §5.1).

UA rules stay the first-pass source of truth; heuristics only ever refine
a "human" verdict, never override a rule hit. Every classification carries
an explainable reason (rule id or heuristic name).
"""

from oriflux.enrichment.crawlers import classify_traffic, refine_traffic


def refined(user_agent: str, *, asn: int = 0, events_last_minute: int = 0) -> tuple[str, str]:
    ua_class, crawler = classify_traffic(user_agent)
    return refine_traffic(
        ua_class, crawler, user_agent=user_agent, asn=asn,
        events_last_minute=events_last_minute,
    )


CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class TestUaRulesStayAuthoritative:
    def test_ai_agent_rule_hit_keeps_its_crawler_name(self) -> None:
        assert refined("Mozilla/5.0 (compatible; GPTBot/1.0)") == ("ai_agent", "ua:GPTBot")

    def test_generic_bot_marker_is_explained(self) -> None:
        traffic_class, reason = refined("curl/8.4.0")
        assert traffic_class == "bot"
        assert reason == "ua:generic"

    def test_rule_hits_are_never_overridden_by_heuristics(self) -> None:
        # a datacenter ASN must not demote an AI agent to plain bot
        assert refined("GPTBot/1.0", asn=16509)[0] == "ai_agent"


class TestBehavioralHeuristics:
    def test_plain_human_stays_human_with_no_reason(self) -> None:
        assert refined(CHROME) == ("human", "")

    def test_headless_browsers_are_bots(self) -> None:
        traffic_class, reason = refined(CHROME.replace("Chrome", "HeadlessChrome"))
        assert traffic_class == "bot"
        assert reason == "heuristic:headless"

    def test_missing_or_tiny_user_agent_is_a_bot(self) -> None:
        assert refined("")[0] == "bot"
        assert refined("Go-http")[1] == "heuristic:no_ua"

    def test_datacenter_asn_with_browser_ua_is_a_bot(self) -> None:
        traffic_class, reason = refined(CHROME, asn=24940)  # Hetzner
        assert traffic_class == "bot"
        assert reason == "heuristic:datacenter_asn"

    def test_residential_asn_stays_human(self) -> None:
        assert refined(CHROME, asn=12322)[0] == "human"  # Free SAS

    def test_inhuman_cadence_is_a_bot(self) -> None:
        traffic_class, reason = refined(CHROME, events_last_minute=90)
        assert traffic_class == "bot"
        assert reason == "heuristic:cadence"

    def test_normal_cadence_stays_human(self) -> None:
        assert refined(CHROME, events_last_minute=12)[0] == "human"
