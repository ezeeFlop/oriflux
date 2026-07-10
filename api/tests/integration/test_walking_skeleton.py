"""Issue #1 acceptance criteria, verified against the running dev stack."""

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
from tests.integration.conftest import API_URL, INGEST_URL, WORKERS_URL

pytestmark = pytest.mark.integration

INGEST_AUTH = {"Authorization": "Bearer dev-ingest-key"}
READ_AUTH = {"Authorization": "Bearer dev-read-key"}


def wide_period() -> dict[str, str]:
    now = datetime.now(tz=UTC)
    return {
        "start": (now - timedelta(days=1)).isoformat(),
        "end": (now + timedelta(days=1)).isoformat(),
    }


def query(payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(f"{API_URL}/api/v1/query", json=payload, headers=READ_AUTH, timeout=10)
    response.raise_for_status()
    return response.json()


def count_pageviews(project_id: str | None = None) -> int:
    payload: dict[str, Any] = {"metric": "pageviews", "period": wide_period()}
    if project_id is not None:
        payload["filters"] = [{"dimension": "project_id", "op": "eq", "value": project_id}]
    results = query(payload)["results"]
    return int(results[0]["value"]) if results else 0


class TestHealthz:
    def test_all_three_services_respond(self) -> None:
        for base in (INGEST_URL, API_URL, WORKERS_URL):
            assert httpx.get(f"{base}/healthz", timeout=5).status_code == 200


class TestEndToEnd:
    def test_pageview_is_queryable_within_5_seconds(self) -> None:
        before = count_pageviews()
        response = httpx.post(
            f"{INGEST_URL}/api/v1/events",
            json={"type": "pageview", "url": f"https://sponge-theory.ai/it-{uuid.uuid4()}"},
            headers=INGEST_AUTH,
            timeout=5,
        )
        assert response.status_code == 202

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if count_pageviews() >= before + 1:
                return
            time.sleep(0.25)
        pytest.fail("pageview did not become queryable within 5 s of ingestion")

    def test_unknown_metric_is_rejected_over_http(self) -> None:
        response = httpx.post(
            f"{API_URL}/api/v1/query",
            json={"metric": "revenue", "period": wide_period()},
            headers=READ_AUTH,
            timeout=5,
        )
        assert response.status_code == 422


class TestAtLeastOnceDedup:
    async def test_redelivered_batch_after_simulated_crash_does_not_double_count(
        self, redis: Redis, settings: Settings
    ) -> None:
        """A batcher killed between insert and XACK re-delivers the same event
        UUIDs on restart. Simulate exactly that: let the live batcher consume
        and insert the event, then insert the very same batch again directly
        (what the restarted batcher would do) and check the count stays 1."""
        project_id = f"proj-dedup-{uuid.uuid4()}"
        wire = PageviewIn.model_validate({"type": "pageview", "url": "https://a.io/dedup"})
        event = EnrichedEvent.from_pageview(
            wire,
            org_id=settings.org_id,
            project_id=project_id,
            timestamp=datetime.now(tz=UTC),
        )

        await publish_event(redis, event)
        deadline = time.monotonic() + 10.0
        while count_pageviews(project_id) < 1:
            if time.monotonic() > deadline:
                pytest.fail("event never inserted by the live batcher")
            await asyncio.sleep(0.25)

        # the re-delivered batch: same event, same UUID, inserted a second time
        ClickHouseSink(get_client(settings)).insert([event])
        await asyncio.sleep(1.0)

        assert count_pageviews(project_id) == 1


class TestSchemaDeclaration:
    def test_events_table_declares_prd_columns_partitioning_and_ttl(
        self, settings: Settings
    ) -> None:
        client = get_client(settings)
        columns = {
            row[0] for row in client.query("DESCRIBE TABLE events").result_rows
        }
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
