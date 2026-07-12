"""Self-host distribution smoke test (issue #71).

Boots the PUBLISHED compose file (deploy/self-host/docker-compose.yml) on
locally-built images, waits for every healthcheck, runs the bootstrap and
asserts it prints an org, keys and the dashboard URL — the exact experience
of a third-party self-hoster, minus the GHCR pull.

Heavy (builds images, runs a second full stack): opt-in via
ORIFLUX_SELFHOST_SMOKE=1 on top of `-m integration`; skipped otherwise.

    ORIFLUX_SELFHOST_SMOKE=1 uv run pytest -m integration tests/integration/test_selfhost_compose.py
"""

import os
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "deploy" / "self-host" / "docker-compose.yml"
PROJECT = "oriflux-selfhost-smoke"

# host ports shifted off the dev stack's (8100/8103) so both can coexist
ENV = {
    "CLICKHOUSE_PASSWORD": "smoke-ch-secret",
    "POSTGRES_PASSWORD": "smoke-pg-secret",
    "ORIFLUX_JWT_SECRET": "smoke-jwt-secret",
    "ORIFLUX_BOOTSTRAP_ORG_SLUG": f"smoke-{uuid.uuid4().hex[:8]}",
    "ORIFLUX_BOOTSTRAP_ORG_NAME": "Smoke Test Org",
    "ORIFLUX_BOOTSTRAP_OWNER_EMAIL": "owner@example.com",
    "ORIFLUX_BOOTSTRAP_PROJECTS": "smoke-product:Smoke Product",
    "ORIFLUX_BOOTSTRAP_APP_URL": "http://localhost:9080",
    "ORIFLUX_REGISTRY": "oriflux-smoke",
    "ORIFLUX_TAG": "smoke",
    "ORIFLUX_WEB_PORT": "9080",
    "ORIFLUX_INGEST_PORT": "9100",
}


def _run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: PLW1510 — check passed per call
        args, env={**os.environ, **ENV}, capture_output=True, text=True, **kwargs  # type: ignore[arg-type]
    )


@pytest.mark.skipif(
    os.environ.get("ORIFLUX_SELFHOST_SMOKE") != "1",
    reason="set ORIFLUX_SELFHOST_SMOKE=1 to run the self-host compose smoke test",
)
def test_selfhost_compose_up_bootstrap() -> None:
    # local single-arch builds under the names the published compose expects
    for image, extra in (
        ("oriflux-smoke/oriflux-api:smoke", []),
        ("oriflux-smoke/oriflux-web:smoke", []),
    ):
        context = REPO_ROOT / ("api" if "api" in image else "web")
        build = _run("docker", "build", "-q", "-t", image, str(context), *extra)
        assert build.returncode == 0, f"build {image} failed:\n{build.stderr}"

    # ingest & workers derive from the api image with their own CMD, exactly
    # like publish-ghcr.sh does
    for image, cmd in (
        (
            "oriflux-smoke/oriflux-ingest:smoke",
            'CMD ["uvicorn", "oriflux.ingest.main:app", "--host", "0.0.0.0",'
            ' "--port", "8000", "--no-access-log"]',
        ),
        ("oriflux-smoke/oriflux-workers:smoke", 'CMD ["bash", "workers-entrypoint.sh"]'),
    ):
        derive = subprocess.run(
            ["docker", "build", "-q", "-t", image, "-f", "-", str(REPO_ROOT / "api")],
            input=f"FROM oriflux-smoke/oriflux-api:smoke\n{cmd}\n",
            env={**os.environ, **ENV},
            capture_output=True,
            text=True,
        )
        assert derive.returncode == 0, f"derive {image} failed:\n{derive.stderr}"

    try:
        up = _run(
            "docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT,
            "up", "-d", "--wait", "--wait-timeout", "240",
        )
        assert up.returncode == 0, f"compose up failed:\n{up.stderr}"

        # --wait already gated on every healthcheck; bootstrap is the last leg
        bootstrap = _run(
            "docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT,
            "exec", "-T", "api", "python", "-m", "oriflux.bootstrap",
        )
        assert bootstrap.returncode == 0, f"bootstrap failed:\n{bootstrap.stderr}"
        out = bootstrap.stdout
        assert f"created org {ENV['ORIFLUX_BOOTSTRAP_ORG_SLUG']}" in out
        assert "ingest key" in out and "ofx_ing_" in out
        assert "read key" in out and "ofx_read_" in out
        assert "dashboard: http://localhost:9080" in out

        # idempotence: a second run creates nothing and reprints no key
        again = _run(
            "docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT,
            "exec", "-T", "api", "python", "-m", "oriflux.bootstrap",
        )
        assert again.returncode == 0
        assert "ofx_ing_" not in again.stdout
    finally:
        _run("docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT, "down", "-v")
