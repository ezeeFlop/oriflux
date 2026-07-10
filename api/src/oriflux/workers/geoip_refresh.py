"""Monthly GeoIP refresh (issues #4, #14 — PRD §5.1).

Default provider is DB-IP Lite (CC-BY 4.0): keyless plain-gzip monthly
files, decompressed and written under the GeoLite2-* names GeoResolver
expects. MaxMind stays available (ORIFLUX_GEOIP_PROVIDER=maxmind) for
deployments that have a license key. Both providers replace the .mmdb
files atomically (os.replace) — GeoResolver reopens on mtime change.
Any problem (bad provider, missing key, network) raises an ops alert and
returns False; it NEVER crashes the worker: stale geo data is strictly
better than no ingestion enrichment at all.
"""

import gzip
import io
import logging
import tarfile
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests

from oriflux.config import Settings

logger = logging.getLogger(__name__)

EDITIONS = ("GeoLite2-City", "GeoLite2-ASN")
_MAXMIND_URL = "https://download.maxmind.com/app/geoip_download"

# DB-IP kind → the file name GeoResolver reads (kept from GeoLite2 so the
# resolver and its fixtures never change — the MMDB format is identical).
_DBIP_KINDS = (("city", "GeoLite2-City.mmdb"), ("asn", "GeoLite2-ASN.mmdb"))

REFRESH_INTERVAL_S = 30 * 24 * 3600  # DB-IP publishes one file per month
RETRY_INTERVAL_S = 6 * 3600  # a transient failure must not mean a month of staleness


def _download(url: str) -> bytes:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def _write_atomically(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        tmp_path.replace(destination)  # atomic: readers never see a half-written DB
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _refresh_dbip(settings: Settings, fetch: Callable[[str], bytes]) -> None:
    month = datetime.now(tz=UTC).strftime("%Y-%m")
    for kind, filename in _DBIP_KINDS:
        url = f"https://download.db-ip.com/free/dbip-{kind}-lite-{month}.mmdb.gz"
        mmdb = gzip.decompress(fetch(url))
        _write_atomically(Path(settings.geoip_dir) / filename, mmdb)
    logger.info("DB-IP Lite databases refreshed in %s", settings.geoip_dir)


def _refresh_maxmind(settings: Settings, fetch: Callable[[str], bytes]) -> None:
    for edition in EDITIONS:
        tarball = fetch(edition)
        _extract_mmdb(tarball, edition, Path(settings.geoip_dir) / f"{edition}.mmdb")
    logger.info("GeoLite2 databases refreshed in %s", settings.geoip_dir)


def _download_maxmind_edition(edition: str, license_key: str) -> bytes:
    response = requests.get(
        _MAXMIND_URL,
        params={"edition_id": edition, "license_key": license_key, "suffix": "tar.gz"},
        timeout=120,
    )
    response.raise_for_status()
    return response.content


def _extract_mmdb(tarball: bytes, edition: str, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        member = next(
            (m for m in tar.getmembers() if m.name.endswith(f"{edition}.mmdb")), None
        )
        if member is None:
            raise ValueError(f"no {edition}.mmdb in the MaxMind archive")
        extracted = tar.extractfile(member)
        assert extracted is not None
        _write_atomically(destination, extracted.read())


def refresh_geoip(
    settings: Settings,
    *,
    alert: Callable[[str], None],
    download: Callable[[str], bytes] | None = None,
) -> bool:
    """Refresh the .mmdb files with the configured provider.

    `download` (injectable for tests) receives a provider-specific source:
    the full URL for dbip, the edition id for maxmind.
    """
    provider = settings.geoip_provider
    if provider == "maxmind" and not settings.maxmind_license_key:
        alert("GeoIP refresh skipped: no MaxMind license key configured (geo stays stale/empty)")
        return False
    try:
        if provider == "dbip":
            _refresh_dbip(settings, download or _download)
        elif provider == "maxmind":
            fetch = download or (
                lambda ed: _download_maxmind_edition(ed, settings.maxmind_license_key)
            )
            _refresh_maxmind(settings, fetch)
        else:
            alert(f"GeoIP refresh skipped: unknown provider {provider!r} (expected dbip|maxmind)")
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — the job must alert, never crash
        # requests errors embed the full URL — for maxmind that includes the
        # license key; redact before the message reaches logs or the ops webhook.
        message = str(exc)
        if settings.maxmind_license_key:
            message = message.replace(settings.maxmind_license_key, "***")
        alert(f"GeoIP refresh FAILED: {message}")
        return False
