"""The one door to inference (issue #33, PRD §6).

Every AI feature calls SPT Models through this gateway — local models
only, never a cloud LLM; the callers only ever hand it AGGREGATES. The
per-org monthly token budget is checked BEFORE each call and every call
lands in the ai_usage ledger (Rayonne lesson: quotas enforced from day
one). Missing settings raise AiDisabled so surfaces degrade cleanly.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.config import Settings
from oriflux.db.models import AiUsage, Organization


class AiDisabled(Exception):
    """SPT Models is not configured — AI surfaces must degrade, not crash."""


class AiBudgetExhausted(Exception):
    """The org burned its monthly inference budget."""


class AiGateway:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        # Own (and therefore later close) the client only if we created it.
        self._owns_client = client is None
        self._client = client or (
            httpx.AsyncClient(base_url=settings.spt_models_url, timeout=60)
            if settings.spt_models_url
            else None
        )

    @property
    def enabled(self) -> bool:
        return bool(self._settings.spt_models_url) and self._client is not None

    async def aclose(self) -> None:
        """Close the httpx client IF this gateway created it.

        A short-lived gateway (the per-run scheduled worker jobs) MUST call
        this: an unclosed AsyncClient leaks its keep-alive connection sockets,
        which is what exhausted the worker's file descriptors in prod. A
        gateway handed an external client leaves it to the caller.
        """
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def _check_budget(self, org_id: str) -> None:
        month_start = datetime.now(tz=UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        org_uuid = uuid.UUID(org_id)
        async with self._session_factory() as session:
            org = await session.get(Organization, org_uuid)
            budget = (
                org.ai_token_budget
                if org is not None and org.ai_token_budget is not None
                else self._settings.ai_default_monthly_token_budget
            )
            spent = (
                await session.execute(
                    select(func.coalesce(func.sum(AiUsage.tokens_in + AiUsage.tokens_out), 0))
                    .where(AiUsage.org_id == org_uuid, AiUsage.created_at >= month_start)
                )
            ).scalar_one()
        if spent >= budget:
            raise AiBudgetExhausted(
                f"monthly AI budget exhausted ({spent}/{budget} tokens)"
            )

    async def _record(self, org_id: str, feature: str, tokens_in: int, tokens_out: int) -> None:
        async with self._session_factory() as session:
            session.add(
                AiUsage(org_id=uuid.UUID(org_id), feature=feature,
                        tokens_in=tokens_in, tokens_out=tokens_out)
            )
            await session.commit()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._settings.spt_models_api_key}"}

    async def chat(
        self,
        org_id: str,
        *,
        feature: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        if not self.enabled or self._client is None:
            raise AiDisabled("SPT Models is not configured")
        await self._check_budget(org_id)
        response = await self._client.post(
            "/v1/chat/completions",
            headers=self._headers(),
            json={
                "model": self._settings.spt_chat_model,
                "messages": messages,
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        usage = payload.get("usage") or {}
        await self._record(
            org_id, feature,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )
        return str(payload["choices"][0]["message"]["content"])

    async def embed(
        self, org_id: str, *, feature: str, texts: list[str]
    ) -> list[list[float]]:
        if not self.enabled or self._client is None:
            raise AiDisabled("SPT Models is not configured")
        await self._check_budget(org_id)
        response = await self._client.post(
            "/v1/embeddings",
            headers=self._headers(),
            json={"model": self._settings.spt_embed_model, "input": texts},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        usage = payload.get("usage") or {}
        await self._record(org_id, feature, int(usage.get("prompt_tokens") or 0), 0)
        return [list(map(float, item["embedding"])) for item in payload["data"]]
