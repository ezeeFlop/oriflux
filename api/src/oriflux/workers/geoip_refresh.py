"""Weekly GeoLite2 refresh (issue #4, PRD §5.1).

Downloads the City and ASN databases with the SPT MaxMind key and replaces
the .mmdb files atomically (os.replace) — GeoResolver reopens on mtime
change. Any problem (missing key, expired key, network) raises an ops
alert and returns False; it NEVER crashes the worker: stale geo data is
strictly better than no ingestion enrichment at all.
"""

import io
import logging
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

import requests

from oriflux.config import Settings

logger = logging.getLogger(__name__)

EDITIONS = ("GeoLite2-City", "GeoLite2-ASN")
_DOWNLOAD_URL = "https://download.maxmind.com/app/geoip_download"

REFRESH_INTERVAL_S = 7 * 24 * 3600
RETRY_INTERVAL_S = 6 * 3600  # a transient failure must not mean a week of staleness


def _download_edition(edition: str, license_key: str) -> bytes:
    response = requests.get(
        _DOWNLOAD_URL,
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
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{edition}.", delete=False
        ) as tmp:
            tmp.write(extracted.read())
            tmp_path = Path(tmp.name)
        try:
            tmp_path.replace(destination)  # atomic: readers never see a half-written DB
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise


def refresh_geoip(
    settings: Settings,
    *,
    alert: Callable[[str], None],
    download: Callable[[str], bytes] | None = None,
) -> bool:
    if not settings.maxmind_license_key:
        alert("GeoIP refresh skipped: no MaxMind license key configured (geo stays stale/empty)")
        return False
    fetch = download or (lambda ed: _download_edition(ed, settings.maxmind_license_key))
    try:
        for edition in EDITIONS:
            tarball = fetch(edition)
            _extract_mmdb(tarball, edition, Path(settings.geoip_dir) / f"{edition}.mmdb")
        logger.info("GeoLite2 databases refreshed in %s", settings.geoip_dir)
        return True
    except Exception as exc:  # noqa: BLE001 — the job must alert, never crash
        # requests errors embed the full URL, license key included — redact
        # before the message reaches logs or the ops webhook.
        message = str(exc).replace(settings.maxmind_license_key, "***")
        alert(f"GeoIP refresh FAILED: {message}")
        return False
