"""Enrichment value objects shared across entrypoints.

They live under `models` (the cross-service contract), not under
`enrichment` (ingest internals), so the shared event model never depends on
ingest implementation modules.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GeoInfo:
    country: str = ""
    region: str = ""
    city: str = ""
    asn: int = 0


@dataclass(frozen=True)
class UAInfo:
    device: str = ""
    os: str = ""
    browser: str = ""
