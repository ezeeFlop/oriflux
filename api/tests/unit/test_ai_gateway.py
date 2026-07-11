"""Seam: the AI gateway (issue #33, PRD §6).

All inference goes through local SPT Models — never a cloud LLM — behind
a per-org token budget enforced BEFORE each call (Rayonne lesson: no
never-enforced quotas). Missing settings = AI cleanly disabled.
"""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.ai.gateway import AiBudgetExhausted, AiDisabled, AiGateway
from oriflux.config import Settings
from oriflux.db.models import AiUsage, Organization

CHAT_RESPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "Bonjour."}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30},
}


def fake_transport(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://spt-models"
    )


async def seed_org(
    sessionmaker: async_sessionmaker[AsyncSession], *, budget: int | None = None
) -> str:
    async with sessionmaker() as session:
        org = Organization(slug="spt", name="SPT", ai_token_budget=budget)
        session.add(org)
        await session.commit()
        return str(org.id)


def make_gateway(
    sessionmaker: async_sessionmaker[AsyncSession],
    handler,  # type: ignore[no-untyped-def]
    **overrides: object,
) -> AiGateway:
    settings = Settings(
        spt_models_url="http://spt-models",
        spt_models_api_key="k",
        spt_chat_model="spt-chat",
        **overrides,  # type: ignore[arg-type]
    )
    return AiGateway(settings, sessionmaker, client=fake_transport(handler))


class TestChat:
    async def test_chat_returns_text_and_records_usage(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        org_id = await seed_org(db_sessionmaker)

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            assert request.headers["authorization"] == "Bearer k"
            return httpx.Response(200, json=CHAT_RESPONSE)

        gateway = make_gateway(db_sessionmaker, handler)
        text = await gateway.chat(
            org_id, feature="ask", messages=[{"role": "user", "content": "salut"}]
        )
        assert text == "Bonjour."
        async with db_sessionmaker() as session:
            [usage] = (await session.execute(select(AiUsage))).scalars().all()
        assert usage.feature == "ask"
        assert usage.tokens_in == 120
        assert usage.tokens_out == 30

    async def test_budget_blocks_before_the_call(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        org_id = await seed_org(db_sessionmaker, budget=100)
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, json=CHAT_RESPONSE)

        gateway = make_gateway(db_sessionmaker, handler)
        await gateway.chat(org_id, feature="ask", messages=[])  # 150 tokens used

        with pytest.raises(AiBudgetExhausted):
            await gateway.chat(org_id, feature="ask", messages=[])
        assert len(calls) == 1  # the second call never reached the model

    async def test_budget_resets_monthly(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        org_id = await seed_org(db_sessionmaker, budget=100)
        async with db_sessionmaker() as session:
            session.add(
                AiUsage(
                    org_id=uuid.UUID(org_id), feature="ask", tokens_in=500, tokens_out=500,
                    created_at=datetime(2026, 6, 1, tzinfo=UTC),  # LAST month
                )
            )
            await session.commit()

        gateway = make_gateway(db_sessionmaker, lambda r: httpx.Response(200, json=CHAT_RESPONSE))
        assert await gateway.chat(org_id, feature="ask", messages=[]) == "Bonjour."

    async def test_missing_settings_means_cleanly_disabled(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        org_id = await seed_org(db_sessionmaker)
        settings = Settings(spt_models_url="")
        gateway = AiGateway(settings, db_sessionmaker)
        with pytest.raises(AiDisabled):
            await gateway.chat(org_id, feature="ask", messages=[])


class TestEmbed:
    async def test_embed_returns_vectors_and_records_usage(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        org_id = await seed_org(db_sessionmaker)

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/embeddings"
            return httpx.Response(200, json={
                "data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}],
                "usage": {"prompt_tokens": 12, "total_tokens": 12},
            })

        gateway = make_gateway(db_sessionmaker, handler, spt_embed_model="spt-embed")
        vectors = await gateway.embed(org_id, feature="segments", texts=["a", "b"])
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]
        async with db_sessionmaker() as session:
            [usage] = (await session.execute(select(AiUsage))).scalars().all()
        assert usage.tokens_in == 12
