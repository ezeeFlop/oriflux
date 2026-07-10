"""Seam: the 60 s in-memory aggregation window (Apitally pattern, §5.3)."""

from oriflux_sdk.aggregator import LATENCY_BUCKETS_MS, Aggregator


def record(agg: Aggregator, **overrides: object) -> None:
    payload: dict = {
        "endpoint": "/items/{item_id}", "method": "GET", "status_code": 200,
        "consumer": "", "ip": "1.2.3.4", "latency_ms": 12.0,
        "bytes_in": 100, "bytes_out": 250,
    }
    payload.update(overrides)
    agg.record(**payload)


class TestAggregation:
    def test_same_key_accumulates(self) -> None:
        agg = Aggregator()
        record(agg)
        record(agg, latency_ms=25.0)
        entries = agg.drain()
        assert len(entries) == 1
        assert entries[0]["count"] == 2
        assert entries[0]["bytes_in"] == 200
        assert entries[0]["bytes_out"] == 500

    def test_distinct_ips_are_distinct_keys(self) -> None:
        """The caller IP is part of the key — that is what makes API geo
        possible despite client-side pre-aggregation (décision 2026-07-10)."""
        agg = Aggregator()
        record(agg, ip="1.1.1.1")
        record(agg, ip="2.2.2.2")
        assert len(agg.drain()) == 2

    def test_latencies_land_in_log_buckets(self) -> None:
        agg = Aggregator()
        record(agg, latency_ms=11.0)  # → bucket 13
        record(agg, latency_ms=12.9)  # → bucket 13
        record(agg, latency_ms=450.0)  # → bucket 500
        hist = agg.drain()[0]["latency_ms"]
        assert hist == {"13": 2, "500": 1}

    def test_latency_beyond_the_last_bucket_clamps(self) -> None:
        agg = Aggregator()
        record(agg, latency_ms=10_000_000.0)
        assert list(agg.drain()[0]["latency_ms"]) == [str(LATENCY_BUCKETS_MS[-1])]

    def test_drain_resets_the_window(self) -> None:
        agg = Aggregator()
        record(agg)
        assert len(agg.drain()) == 1
        assert agg.drain() == []


class TestCardinalityCap:
    def test_overflowing_keys_collapse_into_an_explicit_bucket(self) -> None:
        agg = Aggregator(max_keys=3)
        for i in range(3):
            record(agg, ip=f"10.0.0.{i}")
        record(agg, ip="10.0.9.1")  # 4th distinct key → overflow
        record(agg, ip="10.0.9.2")

        entries = agg.drain()
        overflow = [e for e in entries if e["overflow"]]
        assert len(overflow) == 1
        assert overflow[0]["ip"] == ""  # the IP is dropped, honestly
        assert overflow[0]["count"] == 2
        assert agg.last_overflow_count == 2

    def test_existing_keys_keep_accumulating_after_the_cap(self) -> None:
        agg = Aggregator(max_keys=2)
        record(agg, ip="1.1.1.1")
        record(agg, ip="2.2.2.2")
        record(agg, ip="3.3.3.3")  # overflow
        record(agg, ip="1.1.1.1")  # existing key: still counted exactly
        entries = {e["ip"]: e["count"] for e in agg.drain()}
        assert entries["1.1.1.1"] == 2
