"""Seam: the workers' /healthz must reflect batcher liveness (prod 2026-08-23:
the api-minutely batcher froze for two days while /healthz kept saying ok,
so Swarm never restarted it and Redis filled up to OOM)."""

from httpx import ASGITransport, AsyncClient

from oriflux.workers import main as worker_main


class FakeBatcher:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def is_alive(self, *, max_idle_s: float) -> bool:
        return self._alive


async def _get(app, batchers):
    app.state.batchers = batchers
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://w") as client:
        return await client.get("/healthz")


async def test_healthz_ok_while_all_batchers_tick() -> None:
    app = worker_main.create_app()
    response = await _get(app, [FakeBatcher(True), FakeBatcher(True)])
    assert response.status_code == 200


async def test_healthz_fails_when_a_batcher_is_frozen() -> None:
    app = worker_main.create_app()
    response = await _get(app, [FakeBatcher(True), FakeBatcher(False)])
    assert response.status_code == 503
    assert "frozen" in response.json()["detail"]


async def test_healthz_ok_before_batchers_start() -> None:
    app = worker_main.create_app()
    response = await _get(app, [])
    assert response.status_code == 200
