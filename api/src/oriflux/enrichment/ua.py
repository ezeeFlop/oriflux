"""User-agent parsing into the device/os/browser dimensions (§8.4)."""

from ua_parser import parse

from oriflux.models.enrichment import UAInfo

__all__ = ["UAInfo", "parse_ua"]


def parse_ua(user_agent: str) -> UAInfo:
    if not user_agent:
        return UAInfo()
    result = parse(user_agent)
    return UAInfo(
        device=(result.device.family if result.device else "") or "",
        os=(result.os.family if result.os else "") or "",
        browser=(result.user_agent.family if result.user_agent else "") or "",
    )
