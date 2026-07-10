"""Seam: the weekly GeoLite2 refresh job (issue #4).

Acceptance: runs weekly (worker loop) and survives a missing/expired
MaxMind key with an alert, not a crash.
"""

import io
import tarfile
from pathlib import Path

from oriflux.config import Settings
from oriflux.workers.geoip_refresh import refresh_geoip


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


class TestRefreshGeoip:
    def test_missing_license_key_alerts_instead_of_crashing(self, tmp_path: Path) -> None:
        settings = Settings(maxmind_license_key="", geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        assert refresh_geoip(settings, alert=alert) is False
        assert any("license key" in m for m in alert.messages)

    def test_download_failure_alerts_instead_of_crashing(self, tmp_path: Path) -> None:
        settings = Settings(maxmind_license_key="expired-key", geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        def failing_download(edition: str) -> bytes:
            raise RuntimeError("401 from MaxMind (expired key)")

        assert refresh_geoip(settings, alert=alert, download=failing_download) is False
        assert any("FAILED" in m for m in alert.messages)

    def test_successful_refresh_replaces_the_databases(self, tmp_path: Path) -> None:
        settings = Settings(maxmind_license_key="good-key", geoip_dir=str(tmp_path))
        alert = RecordingAlert()

        def fake_download(edition: str) -> bytes:
            return tarball_with(edition, f"mmdb-bytes-{edition}".encode())

        assert refresh_geoip(settings, alert=alert, download=fake_download) is True
        assert (tmp_path / "GeoLite2-City.mmdb").read_bytes() == b"mmdb-bytes-GeoLite2-City"
        assert (tmp_path / "GeoLite2-ASN.mmdb").read_bytes() == b"mmdb-bytes-GeoLite2-ASN"
        assert alert.messages == []
