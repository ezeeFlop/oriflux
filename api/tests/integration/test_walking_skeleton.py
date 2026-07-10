"""Issues #1/#3 acceptance criteria, verified against the running dev stack."""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis

from oriflux.config import Settings
from oriflux.models.events import EnrichedEvent, PageviewIn
from oriflux.storage.clickhouse import ClickHouseSink, get_client
from oriflux.storage.redis_stream import publish_event
from tests.integration.conftest import API_URL, INGEST_URL, WORKERS_URL, Tenant

pytestmark = pytest.mark.integration


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def wide_period() -> dict[str, str]:
    now = datetime.now(tz=UTC)
    return {
        "start": (now - timedelta(days=1)).isoformat(),
        "end": (now + timedelta(days=1)).isoformat(),
    }


def query(read_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        f"{API_URL}/api/v1/query", json=payload, headers=auth(read_key), timeout=10
    )
    response.raise_for_status()
    return response.json()


def count_pageviews(read_key: str) -> int:
    results = query(read_key, {"metric": "pageviews", "period": wide_period()})["results"]
    return int(results[0]["value"]) if results else 0


class TestHealthz:
    def test_all_three_services_respond(self) -> None:
        for base in (INGEST_URL, API_URL, WORKERS_URL):
            assert httpx.get(f"{base}/healthz", timeout=5).status_code == 200


class TestEndToEnd:
    def test_pageview_is_queryable_within_5_seconds(self, tenant: Tenant) -> None:
        assert count_pageviews(tenant.read_key) == 0  # fresh org
        response = httpx.post(
            f"{INGEST_URL}/api/v1/events",
            json={"type": "pageview", "url": f"https://sponge-theory.ai/it-{uuid.uuid4()}"},
            headers=auth(tenant.ingest_key),
            timeout=5,
        )
        assert response.status_code == 202

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if count_pageviews(tenant.read_key) == 1:
                return
            time.sleep(0.25)
        pytest.fail("pageview did not become queryable within 5 s of ingestion")

    def test_unknown_metric_is_rejected_over_http(self, tenant: Tenant) -> None:
        response = httpx.post(
            f"{API_URL}/api/v1/query",
            json={"metric": "revenue", "period": wide_period()},
            headers=auth(tenant.read_key),
            timeout=5,
        )
        assert response.status_code == 422


class TestKeyEnforcement:
    def test_wrong_scope_keys_are_rejected_both_ways(self, tenant: Tenant) -> None:
        ingest_with_read = httpx.post(
            f"{INGEST_URL}/api/v1/events",
            json={"type": "pageview", "url": "https://a.io/"},
            headers=auth(tenant.read_key),
            timeout=5,
        )
        assert ingest_with_read.status_code == 403
        query_with_ingest = httpx.post(
            f"{API_URL}/api/v1/query",
            json={"metric": "pageviews", "period": wide_period()},
            headers=auth(tenant.ingest_key),
            timeout=5,
        )
        assert query_with_ingest.status_code == 403

    def test_forged_key_is_401_everywhere(self) -> None:
        for url, payload in (
            (f"{INGEST_URL}/api/v1/events", {"type": "pageview", "url": "https://a.io/"}),
            (f"{API_URL}/api/v1/query", {"metric": "pageviews", "period": wide_period()}),
        ):
            response = httpx.post(url, json=payload, headers=auth("ofx_ing_forged"), timeout=5)
            assert response.status_code == 401


class TestOrgIsolation:
    def test_org_a_events_are_invisible_to_org_b(self, tenants: tuple[Tenant, Tenant]) -> None:
        """Issue #3 acceptance: a user of org A cannot read org B data."""
        a, b = tenants
        response = httpx.post(
            f"{INGEST_URL}/api/v1/events",
            json={"type": "pageview", "url": "https://a.io/org-a-only"},
            headers=auth(a.ingest_key),
            timeout=5,
        )
        assert response.status_code == 202

        deadline = time.monotonic() + 10.0
        while count_pageviews(a.read_key) < 1:
            if time.monotonic() > deadline:
                pytest.fail("org A event never became queryable")
            time.sleep(0.25)

        assert count_pageviews(b.read_key) == 0


class TestAtLeastOnceDedup:
    async def test_redelivered_batch_after_simulated_crash_does_not_double_count(
        self, redis: Redis, settings: Settings, tenant: Tenant
    ) -> None:
        """A batcher killed between insert and XACK re-delivers the same event
        UUIDs on restart. Simulate exactly that: let the live batcher consume
        and insert the event, then insert the very same batch again directly
        (what the restarted batcher would do) and check the count stays 1."""
        wire = PageviewIn.model_validate({"type": "pageview", "url": "https://a.io/dedup"})
        event = EnrichedEvent.from_pageview(
            wire,
            org_id=tenant.org_id,
            project_id=tenant.project_id,
            timestamp=datetime.now(tz=UTC),
        )

        await publish_event(redis, event)
        deadline = time.monotonic() + 10.0
        while count_pageviews(tenant.read_key) < 1:
            if time.monotonic() > deadline:
                pytest.fail("event never inserted by the live batcher")
            await asyncio.sleep(0.25)

        # the re-delivered batch: same event, same UUID, inserted a second time
        ClickHouseSink(get_client(settings)).insert([event])
        await asyncio.sleep(1.0)

        assert count_pageviews(tenant.read_key) == 1


class TestSchemaDeclaration:
    def test_events_table_declares_prd_columns_partitioning_and_ttl(
        self, settings: Settings
    ) -> None:
        client = get_client(settings)
        columns = {row[0] for row in client.query("DESCRIBE TABLE events").result_rows}
        required = {
            "timestamp", "org_id", "project_id", "source_type", "event_name",
            "visitor_hash", "session_id", "user_pseudo_id", "tenant_id",
            "url_path", "referrer", "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "country", "region", "city", "asn",
            "device", "os", "browser", "locale", "traffic_class", "props",
        }
        assert required <= columns

        engine_full = client.query(
            "SELECT engine_full FROM system.tables WHERE database = currentDatabase() "
            "AND name = 'events'"
        ).result_rows[0][0]
        assert "PARTITION BY toYYYYMM(timestamp)" in engine_full
        assert "toIntervalMonth(13)" in engine_full or "INTERVAL 13 MONTH" in engine_full
