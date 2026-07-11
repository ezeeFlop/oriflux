"""Live WebSocket channel (issue #39, PRD §12 phase 3).

Replaces the 10 s polling for the live view: one hub task per org
computes ONE registry query batch per tick and fans it out to every
socket of that org — sockets never trigger their own queries. Auth at
the handshake (JWT + org membership, viewer is enough); the dashboard
keeps polling as an automatic fallback, so a broken WS can never blank
the live view. This shares the live view's status as an explicitly
listed non-/query surface: the queries themselves still compile through
the registry.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from oriflux.db.models import Membership, Project, User
from oriflux.query.engine import build_query
from oriflux.query.models import QueryRequest
from oriflux.security.tokens import InvalidToken, decode_access_token

logger = logging.getLogger(__name__)

TICK_S = 5


class QueryExecutor(Protocol):
    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


def _query(executor: QueryExecutor, org_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    request = QueryRequest.model_validate(payload)
    sql, params = build_query(request, org_id=org_id)
    return executor.execute(sql, params)


def build_live_payload(
    executor: QueryExecutor, *, org_id: str, projects: list[tuple[str, str]]
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    live_window = {"start": now - timedelta(seconds=30), "end": now}
    half_hour = {"start": now - timedelta(minutes=30), "end": now}
    tiles = []
    for project_id, name in projects:
        rows = _query(executor, org_id, {
            "metric": "visitors",
            "filters": [{"dimension": "project_id", "op": "eq", "value": project_id}],
            "period": live_window,
        })
        tiles.append({
            "id": project_id, "name": name,
            "live": int(rows[0].get("value") or 0) if rows else 0,
        })
    pages = _query(executor, org_id, {
        "metric": "pageviews", "dimensions": ["page"], "period": half_hour,
    })
    countries = _query(executor, org_id, {
        "metric": "visitors", "dimensions": ["country"], "period": half_hour,
    })
    return {
        "ts": now.isoformat(),
        "projects": tiles,
        "pages": pages[:10],
        "countries": [c for c in countries if c.get("country")][:20],
    }


class LiveHub:
    """org → sockets; one broadcaster task per org while sockets exist."""

    def __init__(self, executor_factory: Any, session_factory: Any) -> None:
        self._executor_factory = executor_factory
        self._session_factory = session_factory
        self._sockets: dict[str, set[WebSocket]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def connect(self, org_id: str, websocket: WebSocket) -> None:
        self._sockets.setdefault(org_id, set()).add(websocket)
        if org_id not in self._tasks or self._tasks[org_id].done():
            self._tasks[org_id] = asyncio.create_task(self._broadcast(org_id))

    def disconnect(self, org_id: str, websocket: WebSocket) -> None:
        self._sockets.get(org_id, set()).discard(websocket)

    async def _broadcast(self, org_id: str) -> None:
        executor = self._executor_factory()
        while self._sockets.get(org_id):
            try:
                async with self._session_factory() as session:
                    projects = [
                        (str(row.id), row.name)
                        for row in (
                            await session.execute(
                                select(Project.id, Project.name).where(
                                    Project.org_id == uuid.UUID(org_id)
                                )
                            )
                        ).all()
                    ]
                payload = await asyncio.to_thread(
                    build_live_payload, executor, org_id=org_id, projects=projects
                )
                for websocket in list(self._sockets.get(org_id, ())):
                    try:
                        await websocket.send_json(payload)
                    except Exception:  # noqa: BLE001 — one dead socket never kills the hub
                        self.disconnect(org_id, websocket)
            except Exception:  # noqa: BLE001
                logger.warning("live broadcast tick failed (org %s)", org_id, exc_info=True)
            await asyncio.sleep(TICK_S)


async def authenticate_ws(websocket: WebSocket) -> str | None:
    """JWT + org from query params (browsers cannot set WS headers)."""
    token = websocket.query_params.get("token", "")
    org = websocket.query_params.get("org", "")
    settings = websocket.app.state.settings
    try:
        user_id = decode_access_token(token, settings)
        org_id = uuid.UUID(org)
    except (InvalidToken, ValueError):
        return None
    async with websocket.app.state.session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None
        membership = await session.get(Membership, (user.id, org_id))
        if membership is None:
            return None
    return str(org_id)


def register_live_endpoint(app: FastAPI, hub: LiveHub) -> None:
    @app.websocket("/api/v1/live")
    async def live(websocket: WebSocket) -> None:
        org_id = await authenticate_ws(websocket)
        if org_id is None:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        await hub.connect(org_id, websocket)
        try:
            while True:
                await websocket.receive_text()  # keepalive pings from the client
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(org_id, websocket)
