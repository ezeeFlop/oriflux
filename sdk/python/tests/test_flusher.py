"""Seam: the flusher must never raise into the host, whatever ingest says —
including a 429 quota rejection (Oriflux issue #60): the payload is dropped,
the breaker records the failure, the host process never sees an exception."""

from oriflux_sdk.aggregator import Aggregator
from oriflux_sdk.flusher import Flusher


class QuotaRejected(Exception):
    pass


def test_quota_429_never_reaches_the_host() -> None:
    aggregator = Aggregator()
    aggregator.record(endpoint="/x", method="GET", status_code=200, latency_ms=1.0, consumer="", ip="", bytes_in=0, bytes_out=0)

    calls: list[object] = []

    def transport(payload: object) -> None:
        calls.append(payload)
        raise QuotaRejected("429 monthly event quota exceeded")

    flusher = Flusher(
        aggregator, api_key="ofx_ing_test", endpoint="http://ingest", transport=transport
    )
    flusher.flush_now()  # must not raise
    assert len(calls) == 1

    # subsequent windows keep flowing (breaker opens only after its threshold)
    aggregator.record(endpoint="/x", method="GET", status_code=200, latency_ms=1.0, consumer="", ip="", bytes_in=0, bytes_out=0)
    flusher.flush_now()
    assert len(calls) == 2
