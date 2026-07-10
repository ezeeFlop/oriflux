"""IP → geo/ASN dimensions via local MaxMind GeoLite2 databases (PRD §5.1, §9).

The IP is resolved here and DISCARDED — only country/region/city/ASN leave
this module; `GeoInfo` never carries the address. Missing or unreadable
databases degrade to empty dimensions (dev environments have no MaxMind
key); readers reopen when the weekly refresh job replaces the .mmdb files.
"""

import contextlib
import logging
from pathlib import Path

import geoip2.database
import geoip2.errors

from oriflux.models.enrichment import GeoInfo

__all__ = ["GeoInfo", "GeoResolver"]

logger = logging.getLogger(__name__)

CITY_DB = "GeoLite2-City.mmdb"
ASN_DB = "GeoLite2-ASN.mmdb"


class _Reader:
    """One .mmdb reader that transparently reopens after file replacement."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._reader: geoip2.database.Reader | None = None
        self._mtime = 0.0

    def get(self) -> geoip2.database.Reader | None:
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            return None
        if self._reader is None or mtime != self._mtime:
            if self._reader is not None:
                self._reader.close()
            try:
                self._reader = geoip2.database.Reader(str(self._path))
                self._mtime = mtime
            except Exception:
                logger.warning("cannot open %s; geo dimensions stay empty", self._path)
                self._reader = None
        return self._reader


class GeoResolver:
    def __init__(self, geoip_dir: Path | str) -> None:
        geoip_dir = Path(geoip_dir)
        self._city = _Reader(geoip_dir / CITY_DB)
        self._asn = _Reader(geoip_dir / ASN_DB)

    def resolve(self, ip: str) -> GeoInfo:
        country = region = city = ""
        asn = 0
        city_reader = self._city.get()
        if city_reader is not None:
            try:
                response = city_reader.city(ip)
                country = response.country.iso_code or ""
                region = (
                    response.subdivisions[0].name if len(response.subdivisions) else ""
                ) or ""
                city = response.city.name or ""
            except (geoip2.errors.AddressNotFoundError, ValueError):
                pass
        asn_reader = self._asn.get()
        if asn_reader is not None:
            with contextlib.suppress(geoip2.errors.AddressNotFoundError, ValueError):
                asn = asn_reader.asn(ip).autonomous_system_number or 0
        return GeoInfo(country=country, region=region, city=city, asn=asn)
