"""Seam: application logging setup (issue #15).

Acceptance: after setup, INFO records from `oriflux.*` loggers reach
stderr (the monthly GeoIP job's success must be observable in prod),
and calling setup twice never duplicates lines.
"""

import logging

import pytest

from oriflux.logs import setup_logging


class TestSetupLogging:
    def test_oriflux_info_records_reach_stderr(self, capfd: pytest.CaptureFixture[str]) -> None:
        setup_logging()

        logging.getLogger("oriflux.workers.geoip_refresh").info("databases refreshed")

        captured = capfd.readouterr()
        assert "databases refreshed" in captured.err

    def test_setup_twice_does_not_duplicate_lines(
        self, capfd: pytest.CaptureFixture[str]
    ) -> None:
        setup_logging()
        setup_logging()

        logging.getLogger("oriflux.test").info("once only")

        captured = capfd.readouterr()
        assert captured.err.count("once only") == 1
