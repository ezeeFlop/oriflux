"""THE canonical crawler / AI-agent list for Sponge Theory properties.

Decision 2026-07-10 (PRD §15.2): this list is maintained in exactly one
place — here — seeded from AudiGEO's `BOT_PATTERNS`
(audigeo/app/services/bots/ingestor.py). AudiGEO becomes a consumer of this
classification via API/MCP in phase 3; until then both lists coexist
deliberately, and additions should land in both.

Phase 1 classification is UA-rules-only (behavioral heuristics arrive in
phase 2): case-insensitive substring match, AI agents checked first.
"""

from typing import Literal

TrafficClass = Literal["human", "bot", "ai_agent"]

# pattern (lowercased at match time) → canonical crawler name
AI_AGENT_PATTERNS: dict[str, str] = {
    # LLM crawlers & assistants — seeded from AudiGEO
    "GPTBot": "GPTBot",
    "ChatGPT-User": "ChatGPT-User",
    "ClaudeBot": "ClaudeBot",
    "anthropic-ai": "ClaudeBot",
    "PerplexityBot": "PerplexityBot",
    "Google-Extended": "Google-Extended",
    "CCBot": "CCBot",
    "cohere-ai": "CohereBot",
    "meta-externalagent": "MetaBot",
    "Applebot-Extended": "Applebot",
    "DuckAssistBot": "DuckAssistBot",
    "YouBot": "YouBot",
    # ByteDance's LLM data crawler (AudiGEO files it under search; it feeds models)
    "Bytespider": "Bytespider",
}

BOT_PATTERNS: dict[str, str] = {
    # search engines — seeded from AudiGEO
    "Googlebot": "Googlebot",
    "bingbot": "bingbot",
}

# Generic markers for the long tail of classic bots (monitors, scrapers,
# CLIs). Accepted phase-1 tradeoff: bare substrings can misfire on exotic
# hardware UAs (e.g. Cubot phones contain "bot") — behavioral heuristics
# refine this in phase 2.
_GENERIC_BOT_MARKERS = ("bot", "crawler", "spider", "curl/", "wget/", "python-requests", "monitor")

# match on lowercase once, at import time — this runs per event
_AI_LOWERED = {pattern.lower(): name for pattern, name in AI_AGENT_PATTERNS.items()}
_BOT_LOWERED = {pattern.lower(): name for pattern, name in BOT_PATTERNS.items()}


def classify_traffic(user_agent: str) -> tuple[TrafficClass, str | None]:
    """UA → (traffic_class, crawler_name). traffic_class ∈ human|bot|ai_agent."""
    ua_lower = user_agent.lower()
    for pattern, name in _AI_LOWERED.items():
        if pattern in ua_lower:
            return "ai_agent", name
    for pattern, name in _BOT_LOWERED.items():
        if pattern in ua_lower:
            return "bot", name
    for marker in _GENERIC_BOT_MARKERS:
        if marker in ua_lower:
            return "bot", None
    return "human", None


# ── Behavioral heuristics (issue #21, phase 2) ──────────────────────────────
# They only ever REFINE a "human" UA verdict — a rule hit is never overridden.
# Pure hosting ASNs only: iCloud Private Relay egresses through Cloudflare and
# Akamai, so CDN ASNs would misclassify millions of legitimate Safari users.
DATACENTER_ASNS: frozenset[int] = frozenset({
    16509,   # Amazon AWS
    14618,   # Amazon AES
    8075,    # Microsoft Azure
    396982,  # Google Cloud
    16276,   # OVH
    24940,   # Hetzner
    14061,   # DigitalOcean
    63949,   # Linode/Akamai Cloud
    20473,   # Vultr
    45102,   # Alibaba Cloud
})

CADENCE_LIMIT_PER_MINUTE = 60  # > 1 event/s sustained is not a person browsing
_MIN_HUMAN_UA_LENGTH = 20


def refine_traffic(
    ua_class: TrafficClass,
    crawler_name: str | None,
    *,
    user_agent: str,
    asn: int = 0,
    events_last_minute: int = 0,
) -> tuple[TrafficClass, str]:
    """(UA verdict, context) → (final class, explainable reason).

    Reasons: "ua:<CrawlerName>" / "ua:generic" for rule hits,
    "heuristic:<name>" when a heuristic reclassified, "" for plain humans.
    """
    if ua_class != "human":
        return ua_class, f"ua:{crawler_name}" if crawler_name else "ua:generic"
    if len(user_agent) < _MIN_HUMAN_UA_LENGTH:
        return "bot", "heuristic:no_ua"
    if "headless" in user_agent.lower():
        return "bot", "heuristic:headless"
    if asn in DATACENTER_ASNS:
        return "bot", "heuristic:datacenter_asn"
    if events_last_minute > CADENCE_LIMIT_PER_MINUTE:
        return "bot", "heuristic:cadence"
    return "human", ""
