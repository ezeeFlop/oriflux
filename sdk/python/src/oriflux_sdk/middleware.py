"""Pure-ASGI middleware — works with FastAPI, Starlette, or any ASGI app.

    from oriflux_sdk import OrifluxMiddleware
    app.add_middleware(OrifluxMiddleware, api_key="ofx_ing_…")

The hot path is dict arithmetic under a lock (< 1 ms guaranteed by test);
everything network-related happens on the flusher thread. Any error in the
recording path is swallowed — Oriflux must never impact the host app.
"""

import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from oriflux_sdk.aggregator import Aggregator
from oriflux_sdk.flusher import Flusher

DEFAULT_ENDPOINT = "https://in.oriflux.sponge-theory.dev"

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
ConsumerFn = Callable[[Scope], str]


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            decoded: str = value.decode("latin-1")
            return decoded
    return ""


def _caller_ip(scope: Scope) -> str:
    # rightmost X-Forwarded-For hop = appended by the product's own proxy;
    # leftmost values are client-controlled
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else ""


class OrifluxMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        api_key: str,
        endpoint: str = DEFAULT_ENDPOINT,
        consumer: ConsumerFn | None = None,
        flush_interval_s: float = 60.0,
        max_keys: int = 2000,
        _autostart: bool = True,
    ) -> None:
        self.app = app
        self._consumer = consumer
        self._aggregator = Aggregator(max_keys=max_keys)
        self._flusher = Flusher(
            self._aggregator,
            api_key=api_key,
            endpoint=endpoint,
            interval_s=flush_interval_s,
        )
        if _autostart:
            self._flusher.start()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500
        bytes_out = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, bytes_out
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                bytes_out += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # never impact the host app, whatever happens in here
            with contextlib.suppress(Exception):
                self._record(scope, status_code, time.perf_counter() - started, bytes_out)

    @staticmethod
    def _endpoint_template(scope: Scope) -> str:
        """The templated route, never the raw path (cardinality!).

        FastAPI sets scope["route"]; plain Starlette only sets path_params,
        so we reverse-substitute them ('/items/42' → '/items/{item_id}')."""
        path: str = getattr(scope.get("route"), "path", None) or scope.get("path", "")
        params = scope.get("path_params") or {}
        if "{" not in path and params:
            segments = path.split("/")
            for name, value in params.items():
                text = str(value)
                segments = [f"{{{name}}}" if seg == text else seg for seg in segments]
            path = "/".join(segments)
        return path[:200]

    def _record(
        self, scope: Scope, status_code: int, elapsed_s: float, bytes_out: int
    ) -> None:
        endpoint = self._endpoint_template(scope)
        try:
            bytes_in = int(_header(scope, b"content-length") or 0)
        except ValueError:
            bytes_in = 0
        self._aggregator.record(
            endpoint=endpoint,
            method=scope.get("method", ""),
            status_code=status_code,
            consumer=self._consumer(scope) if self._consumer else "",
            ip=_caller_ip(scope),
            latency_ms=elapsed_s * 1000.0,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
        )
