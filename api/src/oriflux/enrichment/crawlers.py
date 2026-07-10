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
