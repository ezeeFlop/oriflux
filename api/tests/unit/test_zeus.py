"""Seam: the Zeus infra client (issue #29, PRD §7.2).

Zeus stays the infra source of truth (non-goal §2.2); Oriflux reads its
native FastAPI API with a service-account session. Failures degrade to
None — stale/absent infra data must never break an analytics view.
"""

import httpx

from oriflux.integrations.zeus import ZeusClient
from tests.unit.conftest import login
from tests.unit.test_auth_and_admin import create_org_chain

BASE = "https://zeus.example"


def make_client(handler) -> ZeusClient:  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    return ZeusClient(
        BASE, username="oriflux", password="secret",
        client=httpx.AsyncClient(transport=transport, base_url=BASE),
    )


class TestZeusClient:
    async def test_logs_in_then_reads_service_stats(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(f"{request.method} {request.url.path}")
            if request.url.path == "/api/auth/login":
                return httpx.Response(200, json={"ok": True},
                                      headers={"set-cookie": "session=abc; Path=/"})
            if request.url.path == "/api/cluster/services":
                return httpx.Response(200, json=[
                    {"id": "svc1", "name": "audigeo_api"},
                    {"id": "svc2", "name": "oriflux_api"},
                ])
            if request.url.path == "/api/metrics/services/svc1/containers":
                return httpx.Response(200, json=[
                    {"cpu_percent": 12.5, "memory_mb": 256.0},
                    {"cpu_percent": 7.5, "memory_mb": 128.0},
                ])
            return httpx.Response(404)

        zeus = make_client(handler)
        stats = await zeus.service_stats("audigeo_api")
        assert stats == {"cpu_percent": 20.0, "memory_mb": 384.0, "containers": 2}
        assert calls[0] == "POST /api/auth/login"

    async def test_unknown_service_returns_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return httpx.Response(200, json={"ok": True})
            if request.url.path == "/api/cluster/services":
                return httpx.Response(200, json=[])
            return httpx.Response(404)

        zeus = make_client(handler)
        assert await zeus.service_stats("ghost_service") is None

    async def test_zeus_being_down_degrades_to_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        zeus = make_client(handler)
        assert await zeus.service_stats("audigeo_api") is None


class TestZeusMappingRead:
    async def test_mapping_is_readable_without_zeus_being_up(
        self, api_client: httpx.AsyncClient
    ) -> None:
        """Issue #58: the settings form needs the current mapping even when
        Zeus itself is unreachable or unconfigured."""
        owner = await login(api_client, "alice")
        _, project_id, _ = await create_org_chain(api_client, owner)

        empty = await api_client.get(f"/api/v1/projects/{project_id}/zeus", headers=owner)
        assert empty.status_code == 200
        assert empty.json() == {"zeus_service": None}

        saved = await api_client.patch(
            f"/api/v1/projects/{project_id}/zeus",
            json={"zeus_service": "spt-oriflux_api"},
            headers=owner,
        )
        assert saved.status_code == 200

        read = await api_client.get(f"/api/v1/projects/{project_id}/zeus", headers=owner)
        assert read.json() == {"zeus_service": "spt-oriflux_api"}
