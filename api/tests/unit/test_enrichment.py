"""Seams: the enrichment stage (issue #4) — traffic classification, UA
parsing, geo resolution (IP discarded), and the daily-rotating visitor hash.
"""

from datetime import date
from pathlib import Path

from fakeredis import FakeAsyncRedis

from oriflux.enrichment.crawlers import classify_traffic
from oriflux.enrichment.geo import GeoResolver
from oriflux.enrichment.ua import parse_ua
from oriflux.enrichment.visitor import VisitorHasher

FIXTURES = Path(__file__).parent.parent / "fixtures" / "geoip"

CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
GPTBOT = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot"
CLAUDEBOT = "Mozilla/5.0 AppleWebKit/537.36 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


class TestTrafficClassification:
    """Phase 1: UA rules only; the list is seeded from AudiGEO's (§15.2)."""

    def test_gptbot_is_an_ai_agent(self) -> None:
        assert classify_traffic(GPTBOT) == ("ai_agent", "GPTBot")

    def test_claudebot_is_an_ai_agent(self) -> None:
        assert classify_traffic(CLAUDEBOT) == ("ai_agent", "ClaudeBot")

    def test_perplexity_is_an_ai_agent(self) -> None:
        traffic_class, _ = classify_traffic("Mozilla/5.0 (compatible; PerplexityBot/1.0)")
        assert traffic_class == "ai_agent"

    def test_googlebot_is_a_classic_bot(self) -> None:
        assert classify_traffic(GOOGLEBOT) == ("bot", "Googlebot")

    def test_generic_bot_markers_are_classic_bots(self) -> None:
        assert classify_traffic("FooWatch/2.0 (spider; +https://foo.io)")[0] == "bot"
        assert classify_traffic("curl/8.4.0")[0] == "bot"

    def test_a_browser_is_human(self) -> None:
        assert classify_traffic(CHROME_MAC) == ("human", None)

    def test_empty_ua_is_human_by_default(self) -> None:
        assert classify_traffic("")[0] == "human"


class TestUaParsing:
    def test_browser_os_device_families(self) -> None:
        info = parse_ua(CHROME_MAC)
        assert info.browser == "Chrome"
        assert info.os == "Mac OS X"
        assert info.device == "Mac"

    def test_garbage_ua_yields_empty_fields_not_errors(self) -> None:
        info = parse_ua("")
        assert info.browser in ("", "Other")


class TestGeoResolution:
    """Uses MaxMind's official test databases (fixtures); 81.2.69.142 is the
    canonical London test IP, 1.128.0.1 the canonical AS1221 test IP."""

    def test_known_ip_resolves_to_geo_dimensions(self) -> None:
        resolver = GeoResolver(FIXTURES)
        geo = resolver.resolve("81.2.69.142")
        assert geo.country == "GB"
        assert geo.region == "England"
        assert geo.city == "London"

    def test_asn_is_resolved(self) -> None:
        resolver = GeoResolver(FIXTURES)
        assert resolver.resolve("1.128.0.1").asn == 1221

    def test_missing_databases_degrade_to_empty_not_crash(self, tmp_path: Path) -> None:
        resolver = GeoResolver(tmp_path)
        geo = resolver.resolve("81.2.69.142")
        assert (geo.country, geo.region, geo.city, geo.asn) == ("", "", "", 0)

    def test_invalid_ip_degrades_to_empty(self) -> None:
        resolver = GeoResolver(FIXTURES)
        assert GeoResolver(FIXTURES).resolve("not-an-ip").country == ""
        assert resolver.resolve("10.255.255.255").country == ""  # private, not in DB

    def test_geoinfo_never_carries_the_ip(self) -> None:
        geo = GeoResolver(FIXTURES).resolve("81.2.69.142")
        assert "81.2.69.142" not in repr(geo)


class TestVisitorHash:
    """hash(daily_salt, project_id, ip, user_agent); salt destroyed daily →
    same visitor counts once within a day, anew the next day (PRD §9)."""

    async def test_same_visitor_same_day_hashes_identically(self) -> None:
        hasher = VisitorHasher(FakeAsyncRedis())
        day = date(2026, 7, 10)
        first = await hasher.visitor_hash("proj", "1.2.3.4", CHROME_MAC, day=day)
        second = await hasher.visitor_hash("proj", "1.2.3.4", CHROME_MAC, day=day)
        assert first == second

    async def test_salt_rotation_makes_a_new_visitor_the_next_day(self) -> None:
        hasher = VisitorHasher(FakeAsyncRedis())
        today = await hasher.visitor_hash("proj", "1.2.3.4", CHROME_MAC, day=date(2026, 7, 10))
        tomorrow = await hasher.visitor_hash("proj", "1.2.3.4", CHROME_MAC, day=date(2026, 7, 11))
        assert today != tomorrow

    async def test_different_projects_never_share_a_hash(self) -> None:
        """No cross-site tracking: project_id is part of the hash input."""
        hasher = VisitorHasher(FakeAsyncRedis())
        day = date(2026, 7, 10)
        a = await hasher.visitor_hash("proj-a", "1.2.3.4", CHROME_MAC, day=day)
        b = await hasher.visitor_hash("proj-b", "1.2.3.4", CHROME_MAC, day=day)
        assert a != b

    async def test_the_daily_salt_expires(self) -> None:
        redis = FakeAsyncRedis()
        hasher = VisitorHasher(redis)
        await hasher.visitor_hash("proj", "1.2.3.4", CHROME_MAC, day=date(2026, 7, 10))
        keys = await redis.keys("oriflux:visitor_salt:*")
        assert len(keys) == 1
        assert await redis.ttl(keys[0]) > 0  # destruction is scheduled, not optional

    async def test_the_hash_does_not_reveal_the_ip(self) -> None:
        hasher = VisitorHasher(FakeAsyncRedis())
        value = await hasher.visitor_hash("proj", "81.2.69.142", CHROME_MAC, day=date(2026, 7, 10))
        assert "81.2.69.142" not in value
        assert len(value) == 64  # sha256 hex
