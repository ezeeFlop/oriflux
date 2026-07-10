"""Issue #11 UC4 e2e: a real 5xx spike > 2 % over 5 min fires a Slack-shaped
webhook within one evaluation cycle.

Real pieces: 5xx workload through the live ingest → batcher → ClickHouse;
registry-compiled evaluation; actual HTTP delivery to a local sink. The
rule lives in an in-memory store (not the shared PG) so the container's own
evaluator can't race this test's notifications.
"""

import http.server
import json
import threading
import time
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from oriflux.alerting.evaluator import Evaluator
from oriflux.alerting.notify import AlertNotifier
from oriflux.config import Settings
from oriflux.db.models import AlertRule, Base
from oriflux.storage.clickhouse import ClickHouseExecutor, get_client
from tests.integration.conftest import INGEST_URL, Tenant

pytestmark = pytest.mark.integration


class SlackSink(http.server.BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        SlackSink.received.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def slack_sink() -> str:
    SlackSink.received = []
    server = http.server.HTTPServer(("127.0.0.1", 0), SlackSink)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"https://127.0.0.1:{server.server_port}".replace("https", "http")
    server.shutdown()


@pytest.fixture
async def rule_store() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class TestUc4:
    async def test_a_5xx_spike_fires_slack_within_one_cycle(
        self,
        tenant: Tenant,
        settings: Settings,
        slack_sink: str,
        rule_store: async_sessionmaker[AsyncSession],
    ) -> None:
        # 1. the spike: 100 requests, 10 of them 5xx (10 % > 2 %) via live ingest
        spike = {
            "window_start": datetime.now(tz=UTC).isoformat(),
            "overflow_count": 0,
            "entries": [
                {"endpoint": "/spiky", "method": "GET", "status_code": 200,
                 "consumer": "", "ip": "", "count": 90, "latency_ms": {"10": 90},
                 "overflow": False},
                {"endpoint": "/spiky", "method": "GET", "status_code": 503,
                 "consumer": "", "ip": "", "count": 10, "latency_ms": {"100": 10},
                 "overflow": False},
            ],
        }
        posted = httpx.post(
            f"{INGEST_URL}/api/v1/api-metrics",
            json=spike,
            headers={"Authorization": f"Bearer {tenant.ingest_key}"},
            timeout=5,
        )
        assert posted.status_code == 202

        executor = ClickHouseExecutor(get_client(settings))
        deadline = time.monotonic() + 10.0
        while not executor.execute(
            "SELECT count() AS value FROM api_minutely WHERE org_id = {o:String}",
            {"o": tenant.org_id},
        )[0]["value"]:
            if time.monotonic() > deadline:
                pytest.fail("spike rows never reached ClickHouse")
            time.sleep(0.25)

        # 2. the rule (UC4): 5xx rate > 2 % over 5 min
        async with rule_store() as session:
            session.add(
                AlertRule(
                    org_id=uuid.UUID(tenant.org_id),
                    name="AudiGEO API 5xx",
                    metric="api_error_rate_5xx",
                    filters=[],
                    condition="gt",
                    threshold=2.0,
                    window_minutes=5,
                    slack_webhook_url=slack_sink,
                )
            )
            await session.commit()

        # 3. one evaluation cycle → Slack message delivered over real HTTP
        evaluator = Evaluator(
            rule_store,
            executor,
            AlertNotifier(Settings(allow_private_webhooks=True)),
        )
        await evaluator.run_once(now=datetime.now(tz=UTC))

        assert len(SlackSink.received) == 1
        text = SlackSink.received[0]["text"]
        assert "ALERT" in text
        assert "api_error_rate_5xx" in text

        # 4. sustained breach: second cycle stays silent (cooldown/dedup)
        await evaluator.run_once(now=datetime.now(tz=UTC))
        assert len(SlackSink.received) == 1
