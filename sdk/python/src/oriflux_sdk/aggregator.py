"""Client-side 60 s aggregation window (Apitally pattern, PRD §5.3).

Requests are counted per (endpoint template, method, status code, consumer,
caller IP) — the IP in the key is what makes API geo possible despite
pre-aggregation: ingest resolves it to country/ASN then discards it.
Latencies land in fixed log-spaced buckets so the payload stays tiny.

Cardinality is hard-capped: once `max_keys` distinct keys exist in the
window, NEW keys collapse into one overflow bucket per (endpoint, method,
status, consumer) with the IP dropped — the data stays honest about itself
(geo shows as unresolved server-side) instead of growing without bound.
"""

import threading
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Any

LATENCY_BUCKETS_MS: tuple[int, ...] = (
    1, 2, 3, 5, 8, 13, 20, 30, 50, 80, 130, 200, 300, 500, 800,
    1300, 2000, 3000, 5000, 8000, 13000, 20000, 30000,
)

_Key = tuple[str, str, int, str, str]  # endpoint, method, status, consumer, ip


def _bucket_for(latency_ms: float) -> int:
    index = bisect_left(LATENCY_BUCKETS_MS, latency_ms)
    return LATENCY_BUCKETS_MS[min(index, len(LATENCY_BUCKETS_MS) - 1)]


@dataclass
class _Cell:
    count: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    histogram: dict[int, int] = field(default_factory=dict)
    overflow: bool = False


class Aggregator:
    def __init__(self, max_keys: int = 2000) -> None:
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._window: dict[_Key, _Cell] = {}
        self._overflow_count = 0
        self.last_overflow_count = 0

    def record(
        self,
        *,
        endpoint: str,
        method: str,
        status_code: int,
        consumer: str,
        ip: str,
        latency_ms: float,
        bytes_in: int,
        bytes_out: int,
    ) -> None:
        key: _Key = (endpoint, method, status_code, consumer, ip)
        bucket = _bucket_for(latency_ms)
        with self._lock:
            cell = self._window.get(key)
            if cell is None:
                if len(self._window) >= self._max_keys:
                    key = (endpoint, method, status_code, consumer, "")
                    cell = self._window.get(key)
                    if cell is None or not cell.overflow:
                        cell = self._window.setdefault(key, _Cell(overflow=True))
                        cell.overflow = True
                    self._overflow_count += 1
                else:
                    cell = _Cell()
                    self._window[key] = cell
            cell.count += 1
            cell.bytes_in += bytes_in
            cell.bytes_out += bytes_out
            cell.histogram[bucket] = cell.histogram.get(bucket, 0) + 1

    def drain(self) -> list[dict[str, Any]]:
        """Return the window's entries and start a fresh window."""
        with self._lock:
            window, self._window = self._window, {}
            self.last_overflow_count, self._overflow_count = self._overflow_count, 0
        return [
            {
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "consumer": consumer,
                "ip": ip,
                "count": cell.count,
                "bytes_in": cell.bytes_in,
                "bytes_out": cell.bytes_out,
                "latency_ms": {str(bucket): n for bucket, n in sorted(cell.histogram.items())},
                "overflow": cell.overflow,
            }
            for (endpoint, method, status_code, consumer, ip), cell in window.items()
        ]
