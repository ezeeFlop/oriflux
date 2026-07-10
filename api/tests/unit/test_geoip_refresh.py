"""Seam: the monthly GeoIP refresh job (issues #4, #14).

Acceptance: fills the .mmdb files without any key via DB-IP Lite (the
default provider), keeps MaxMind working when a key is configured, and
survives any failure with an alert, not a crash.
"""

import gzip
import io
import os
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path

from oriflux.config import Settings
from oriflux.workers.geoip_refresh import REFRESH_INTERVAL_S, maybe_refresh_geoip, refresh_geoip


def tarball_with(edition: str, content: bytes) -> bytes:
    """A MaxMind-shaped tar.gz: <edition>_<date>/<edition>.mmdb"""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=f"{edition}_20260710/{edition}.mmdb")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class RecordingAlert:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


class TestRefreshDbip:
    """DB-IP Lite is the default provider: keyless, plain-gzip monthly files."""

    def test_keyless_refresh_fills_the_georesolver_databases(self, tmp_path: Path) -> None:
        settings = Settings(maxmind_license_key="", geoip_dir=str(tmp_path))
        alert = RecordingAlert()
        requested: list[str] = []

        def fake_download(url: str) -> bytes:
            requested.append(url)
            kind = "city" if "city" in url else "asn"
            return gzip.compress(f"mmdb-bytes-{kind}".encode())

        assert refresh_geoip(settings, alert=alert, download=fake_download) is True
        month = datetime.now(tz=UTC).strftime("%Y-%m")
        assert requested == [
            f"https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz",
            f"https://download.db-ip.com/free/dbip-asn-lite-{month}.mmdb.gz",
        ]
        assert (tmp_path / "GeoLite2-City.mmdb").read_bytes() == b"mmdb-bytes-city"
        assert (tmp_path / "GeoLite2-ASN.mmdb").read_bytes() == b"mmdb-bytes-asn"
        assert alert.messages == []

    def test_download_failure_alerts_instead_of_crashing(self, tmp_path: Path) -> None:
        settings = Settings(geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        def failing_download(url: str) -> bytes:
            raise RuntimeError("404 from db-ip.com")

        assert refresh_geoip(settings, alert=alert, download=failing_download) is False
        assert any("FAILED" in m for m in alert.messages)


class TestRefreshMaxmind:
    """MaxMind stays available for deployments that have a license key."""

    def test_missing_license_key_alerts_instead_of_crashing(self, tmp_path: Path) -> None:
        settings = Settings(
            geoip_provider="maxmind", maxmind_license_key="", geoip_dir=str(tmp_path)
        )
        alert = RecordingAlert()

        assert refresh_geoip(settings, alert=alert) is False
        assert any("license key" in m for m in alert.messages)

    def test_download_failure_redacts_the_key_in_the_alert(self, tmp_path: Path) -> None:
        settings = Settings(
            geoip_provider="maxmind", maxmind_license_key="expired-key", geoip_dir=str(tmp_path)
        )
        alert = RecordingAlert()

        def failing_download(edition: str) -> bytes:
            raise RuntimeError("401 from MaxMind (key expired-key rejected)")

        assert refresh_geoip(settings, alert=alert, download=failing_download) is False
        assert any("FAILED" in m for m in alert.messages)
        assert all("expired-key" not in m for m in alert.messages)

    def test_successful_refresh_replaces_the_databases(self, tmp_path: Path) -> None:
        settings = Settings(
            geoip_provider="maxmind", maxmind_license_key="good-key", geoip_dir=str(tmp_path)
        )
        alert = RecordingAlert()

        def fake_download(edition: str) -> bytes:
            return tarball_with(edition, f"mmdb-bytes-{edition}".encode())

        assert refresh_geoip(settings, alert=alert, download=fake_download) is True
        assert (tmp_path / "GeoLite2-City.mmdb").read_bytes() == b"mmdb-bytes-GeoLite2-City"
        assert (tmp_path / "GeoLite2-ASN.mmdb").read_bytes() == b"mmdb-bytes-GeoLite2-ASN"
        assert alert.messages == []


class TestMaybeRefreshGeoip:
    """The 6 h beat tick calls this: refresh only when the databases are stale.

    Preserves the two cadences from the asyncio loop (issue #16): a failure
    is retried at the next 6 h tick, a success keeps files fresh for a month.
    """

    def _touch_databases(self, geoip_dir: Path, age_s: float) -> None:
        stamp = time.time() - age_s
        for name in ("GeoLite2-City.mmdb", "GeoLite2-ASN.mmdb"):
            path = geoip_dir / name
            path.write_bytes(b"mmdb")
            os.utime(path, (stamp, stamp))

    def test_fresh_databases_skip_the_download(self, tmp_path: Path) -> None:
        self._touch_databases(tmp_path, age_s=3600)
        settings = Settings(geoip_dir=str(tmp_path))
        alert = RecordingAlert()
        calls: list[str] = []

        def download(url: str) -> bytes:
            calls.append(url)
            return gzip.compress(b"x")

        assert maybe_refresh_geoip(settings, alert=alert, download=download) is True
        assert calls == []
        assert alert.messages == []

    def test_stale_databases_trigger_a_refresh(self, tmp_path: Path) -> None:
        self._touch_databases(tmp_path, age_s=REFRESH_INTERVAL_S + 3600)
        settings = Settings(geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        def download(url: str) -> bytes:
            return gzip.compress(b"fresh")

        assert maybe_refresh_geoip(settings, alert=alert, download=download) is True
        assert (tmp_path / "GeoLite2-City.mmdb").read_bytes() == b"fresh"

    def test_missing_databases_trigger_a_refresh(self, tmp_path: Path) -> None:
        settings = Settings(geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        def download(url: str) -> bytes:
            return gzip.compress(b"fresh")

        assert maybe_refresh_geoip(settings, alert=alert, download=download) is True
        assert (tmp_path / "GeoLite2-ASN.mmdb").read_bytes() == b"fresh"


class TestUnknownProvider:
    def test_unknown_provider_alerts_instead_of_crashing(self, tmp_path: Path) -> None:
        settings = Settings(geoip_provider="ip2location", geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        assert refresh_geoip(settings, alert=alert) is False
        assert any("unknown provider" in m for m in alert.messages)
