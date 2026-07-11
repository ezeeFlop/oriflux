"""Zeus infra client (issue #29, PRD §7.2).

Zeus keeps infrastructure monitoring (non-goal §2.2) — Oriflux only READS
its native FastAPI API (no Prometheus, per the Zeus architecture decision)
with a service-account session. Every failure degrades to None: absent
infra data must never break an analytics view. NOTE: Zeus exposes no
per-service time series today, so correlation is a live snapshot
(cpu/mem summed over the service's containers), not an overlay — noted
on the issue.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ZeusClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str,
        password: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10)
        self._username = username
        self._password = password
        self._authenticated = False

    async def _login(self) -> None:
        response = await self._client.post(
            "/api/auth/login",
            json={"username": self._username, "password": self._password},
        )
        response.raise_for_status()
        self._authenticated = True

    async def _get(self, path: str) -> Any:
        if not self._authenticated:
            await self._login()
        response = await self._client.get(path)
        if response.status_code == 401:  # session expired: one re-login
            await self._login()
            response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def service_stats(self, service_name: str) -> dict[str, float | int] | None:
        """Live CPU/RAM snapshot for a Swarm service, or None on any failure."""
        try:
            services = await self._get("/api/cluster/services")
            service_id = next(
                (s.get("id") for s in services if s.get("name") == service_name), None
            )
            if service_id is None:
                return None
            containers = await self._get(f"/api/metrics/services/{service_id}/containers")
            if not isinstance(containers, list) or not containers:
                return None
            return {
                "cpu_percent": round(
                    sum(float(c.get("cpu_percent") or 0) for c in containers), 1
                ),
                "memory_mb": round(
                    sum(float(c.get("memory_mb") or 0) for c in containers), 1
                ),
                "containers": len(containers),
            }
        except Exception:  # noqa: BLE001 — stale/absent infra data is acceptable
            logger.warning("zeus unreachable or unexpected response", exc_info=True)
            self._authenticated = False
            return None
