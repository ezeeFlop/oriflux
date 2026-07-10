"""Shared unit-test fixtures: in-memory DB and an api app with faked boundaries.

The endpoint tests run the real app over aiosqlite (portable column types);
PostgreSQL-backed equivalents run in tests/integration against the compose
stack. External boundaries (Google verification, ClickHouse) are faked.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from oriflux.api.main import create_app
from oriflux.config import Settings
from oriflux.db.models import Base
from oriflux.security.google import GoogleIdentity, GoogleVerificationError

TEST_SETTINGS = Settings(jwt_secret="unit-test-secret")


class FakeGoogle:
    """token string → identity; anything unknown fails verification."""

    def __init__(self) -> None:
        self.identities: dict[str, GoogleIdentity] = {
            "google-token-alice": GoogleIdentity(
                sub="sub-alice", email="alice@sponge-theory.io", name="Alice"
            ),
            "google-token-bob": GoogleIdentity(
                sub="sub-bob", email="bob@sponge-theory.io", name="Bob"
            ),
        }

    def __call__(self, token: str) -> GoogleIdentity:
        try:
            return self.identities[token]
        except KeyError as exc:
            raise GoogleVerificationError("invalid token") from exc


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.rows: list[dict[str, Any]] = [{"value": 0}]

    def execute(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((sql, params))
        return self.rows


@pytest.fixture
async def db_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def fake_executor() -> FakeExecutor:
    return FakeExecutor()


@pytest.fixture
async def api_client(
    db_sessionmaker: async_sessionmaker[AsyncSession], fake_executor: FakeExecutor
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        executor=fake_executor,
        settings=TEST_SETTINGS,
        session_factory=db_sessionmaker,
        google_verifier=FakeGoogle(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


async def login(client: httpx.AsyncClient, who: str = "alice") -> dict[str, str]:
    """Log in via the faked Google flow; returns auth headers."""
    response = await client.post("/api/v1/auth/google", json={"id_token": f"google-token-{who}"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
