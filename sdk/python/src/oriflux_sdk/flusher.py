"""Async flush of the aggregation window — fire-and-forget, breaker-guarded.

A daemon thread wakes every `interval` seconds, drains the window and POSTs
it to the ingest endpoint (stdlib urllib: the SDK has zero dependencies).
Failures are dropped, never retried, never raised: bounded memory and zero
impact on the instrumented API are worth more than a minute of metrics.
After `failure_threshold` consecutive failures the breaker opens and
flushes are skipped entirely until `cooldown_s` passes.
"""

import json
import logging
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from oriflux_sdk.aggregator import Aggregator

logger = logging.getLogger("oriflux_sdk")

Transport = Callable[[dict[str, Any]], None]


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._consecutive_failures = 0
        self._open_until = 0.0

    def allow(self) -> bool:
        return self._clock() >= self._open_until

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._open_until = self._clock() + self._cooldown_s
            self._consecutive_failures = 0
            logger.warning("oriflux ingest unreachable; pausing flushes for %.0fs",
                           self._cooldown_s)


def _http_transport(url: str, api_key: str, timeout_s: float) -> Transport:
    def send(payload: dict[str, Any]) -> None:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "oriflux-sdk-python",
            },
            method="POST",
        )
        urllib.request.urlopen(request, timeout=timeout_s).close()

    return send


class Flusher:
    def __init__(
        self,
        aggregator: Aggregator,
        *,
        api_key: str,
        endpoint: str,
        interval_s: float = 60.0,
        timeout_s: float = 3.0,
        transport: Transport | None = None,
    ) -> None:
        self._aggregator = aggregator
        self._interval_s = interval_s
        url = endpoint.rstrip("/") + "/api/v1/api-metrics"
        self._transport: Transport = transport or _http_transport(url, api_key, timeout_s)
        self._breaker = CircuitBreaker()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="oriflux-sdk-flusher", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_s):
            self.flush_now()

    def flush_now(self) -> None:
        try:
            entries = self._aggregator.drain()
            if not entries or not self._breaker.allow():
                return  # dropped by design: bounded memory, zero host impact
            payload = {
                "window_start": datetime.now(tz=timezone.utc).isoformat(),
                "overflow_count": self._aggregator.last_overflow_count,
                "entries": entries,
            }
            try:
                self._transport(payload)
                self._breaker.record_success()
            except Exception:
                self._breaker.record_failure()
        except Exception:  # noqa: BLE001 — the flusher may never take the host down
            logger.debug("oriflux flush failed", exc_info=True)
