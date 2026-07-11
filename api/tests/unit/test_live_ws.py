"""Seam: the live WebSocket channel (issue #39, PRD §12 phase 3).

One registry query batch per org per tick, shared across that org's
sockets; JWT+org auth at the handshake; a broken socket must never take
the hub down.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from oriflux.api.live import build_live_payload


class FlatExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls += 1
        if "GROUP BY" in sql and "url_path" in sql:
            return [{"page": "/docs", "value": 3}]
        if "GROUP BY" in sql and "country" in sql:
            return [{"country": "FR", "value": 2}]
        return [{"value": 5}]


class TestLivePayload:
    def test_payload_carries_projects_pages_and_countries(self) -> None:
        executor = FlatExecutor()
        payload = build_live_payload(
            executor, org_id="org-1", projects=[("p1", "AudiGEO"), ("p2", "NeoRAG")]
        )
        assert payload["projects"] == [
            {"id": "p1", "name": "AudiGEO", "live": 5},
            {"id": "p2", "name": "NeoRAG", "live": 5},
        ]
        assert payload["pages"][0]["page"] == "/docs"
        assert payload["countries"][0]["country"] == "FR"

    def test_one_batch_per_tick(self) -> None:
        executor = FlatExecutor()
        build_live_payload(executor, org_id="org-1", projects=[("p1", "A"), ("p2", "B")])
        # 2 live queries (one per project) + pages + countries = 4, not per-socket
        assert executor.calls == 4


@pytest.fixture
def ws_client(db_sessionmaker, fake_executor):  # type: ignore[no-untyped-def]
    from oriflux.api.main import create_app
    from oriflux.config import Settings

    settings = Settings()
    app = create_app(
        executor=fake_executor, settings=settings, session_factory=db_sessionmaker
    )
    return TestClient(app), settings


class TestLiveEndpoint:
    def test_bad_token_is_refused(self, ws_client) -> None:  # type: ignore[no-untyped-def]
        from starlette.websockets import WebSocketDisconnect

        client, _ = ws_client
        with pytest.raises(WebSocketDisconnect) as excinfo, client.websocket_connect(
            "/api/v1/live?token=bad&org=none"
        ):
            pass
        assert excinfo.value.code == 4401
