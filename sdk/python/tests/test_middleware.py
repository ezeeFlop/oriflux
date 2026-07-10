"""Seam: the ASGI middleware — 3-line FastAPI/Starlette integration.

Records must be keyed by the ROUTE TEMPLATE (not the raw path), the record
path must never raise into the host app, and flushing must go through the
circuit breaker so Oriflux downtime cannot impact the instrumented API.
"""

import asyncio
import time

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from oriflux_sdk import OrifluxMiddleware
from oriflux_sdk.flusher import CircuitBreaker


async def get_item(request):  # type: ignore[no-untyped-def]
    if request.path_params["item_id"] == "boom":
        return JSONResponse({"error": "nope"}, status_code=500)
    return JSONResponse({"ok": True})


def make_app() -> tuple[OrifluxMiddleware, Starlette]:
    app = Starlette(routes=[Route("/items/{item_id}", get_item)])
    middleware = OrifluxMiddleware(
        app, api_key="ofx_ing_test", _autostart=False  # flusher driven manually in tests
    )
    return middleware, app


async def call(middleware: OrifluxMiddleware, path: str, headers: dict | None = None) -> int:
    transport = httpx.ASGITransport(app=middleware)
    async with httpx.AsyncClient(transport=transport, base_url="http://it") as client:
        return (await client.get(path, headers=headers)).status_code


class TestRecording:
    async def test_requests_are_keyed_by_route_template(self) -> None:
        middleware, _ = make_app()
        await call(middleware, "/items/1")
        await call(middleware, "/items/2")
        entries = middleware._aggregator.drain()
        assert len(entries) == 1
        assert entries[0]["endpoint"] == "/items/{item_id}"
        assert entries[0]["count"] == 2

    async def test_status_codes_split_keys(self) -> None:
        middleware, _ = make_app()
        await call(middleware, "/items/1")
        await call(middleware, "/items/boom")
        by_status = {e["status_code"]: e["count"] for e in middleware._aggregator.drain()}
        assert by_status == {200: 1, 500: 1}

    async def test_forwarded_ip_is_recorded_from_the_proxy_hop(self) -> None:
        middleware, _ = make_app()
        await call(middleware, "/items/1", headers={"X-Forwarded-For": "6.6.6.6, 10.1.1.1"})
        assert middleware._aggregator.drain()[0]["ip"] == "10.1.1.1"

    async def test_recording_failures_never_reach_the_host_app(self) -> None:
        middleware, _ = make_app()
        middleware._aggregator.record = None  # type: ignore[assignment] — sabotage
        assert await call(middleware, "/items/1") == 200


class TestOverhead:
    async def test_record_path_is_under_1ms_p99(self) -> None:
        """NFR §11 / acceptance: < 1 ms per request added by the middleware."""
        middleware, app = make_app()

        async def drive(asgi_app, n: int = 300) -> list[float]:
            transport = httpx.ASGITransport(app=asgi_app)
            samples = []
            async with httpx.AsyncClient(transport=transport, base_url="http://it") as client:
                for _ in range(n):
                    t0 = time.perf_counter()
                    await client.get("/items/1")
                    samples.append(time.perf_counter() - t0)
            return sorted(samples)

        raw = await drive(app)
        wrapped = await drive(middleware)
        p99_added = wrapped[int(len(wrapped) * 0.99)] - raw[int(len(raw) * 0.99)]
        assert p99_added < 0.001, f"p99 overhead {p99_added * 1000:.2f} ms"


class FailingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload: dict) -> None:
        self.calls += 1
        raise ConnectionError("ingest is down")


class TestCircuitBreaker:
    def test_opens_after_consecutive_failures_and_recovers_after_cooldown(self) -> None:
        clock = [0.0]
        breaker = CircuitBreaker(failure_threshold=3, cooldown_s=300, clock=lambda: clock[0])
        for _ in range(3):
            assert breaker.allow()
            breaker.record_failure()
        assert not breaker.allow()  # open: flushes are skipped, payloads dropped
        clock[0] = 301.0
        assert breaker.allow()  # half-open: one attempt goes through
        breaker.record_success()
        assert breaker.allow()

    async def test_ingest_down_leaves_the_host_app_unaffected(self) -> None:
        middleware, _ = make_app()
        transport = FailingTransport()
        middleware._flusher._transport = transport
        middleware._flusher._breaker = CircuitBreaker(
            failure_threshold=2, cooldown_s=300, clock=time.monotonic
        )

        for _ in range(5):
            assert await call(middleware, "/items/1") == 200
            await asyncio.to_thread(middleware._flusher.flush_now)

        # breaker opened after 2 failures: no further transport calls
        assert transport.calls == 2
        assert await call(middleware, "/items/1") == 200
