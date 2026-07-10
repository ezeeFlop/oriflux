"""Programmatic alembic upgrade, run at api-service startup.

Runs in a worker thread (alembic's async env.py calls asyncio.run, which
must not happen on the running event loop). Retries while PostgreSQL comes
up — Swarm gives no start ordering.
"""

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config

from oriflux.config import Settings

logger = logging.getLogger(__name__)

_SCRIPT_LOCATION = Path(__file__).parent / "migrations"


def run_migrations(settings: Settings, *, attempts: int = 30, delay_s: float = 2.0) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)

    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            command.upgrade(cfg, "head")
            return
        except Exception as exc:  # noqa: BLE001 — retry while PG comes up
            last_error = exc
            logger.warning("migration attempt failed (%s); retrying in %.0fs", exc, delay_s)
            time.sleep(delay_s)
    raise RuntimeError(f"migrations failed after {attempts} attempts") from last_error
