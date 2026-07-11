"""Seam: Ask Oriflux — NL → typed QueryRequest (issue #34, PRD §6).

The model only ever emits a QueryRequest JSON validated by the registry;
hallucinations die at schema validation with ONE guided repair round.
Never generated SQL, and the caller gets the compiled object back for
auditability.
"""

import json

import httpx
import pytest

from oriflux.ai.ask import AskCompilationError, compile_question, registry_vocabulary

GOOD = json.dumps(
    {
        "metric": "visitors",
        "dimensions": ["country"],
        "period": {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"},
    }
)


class FakeGateway:
    """Scripted chat responses; records every message it was sent."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.conversations: list[list[dict[str, str]]] = []

    async def chat(self, org_id: str, *, feature: str, messages, temperature=0.2):  # type: ignore[no-untyped-def]
        self.conversations.append(list(messages))
        return self.responses.pop(0)


class TestVocabulary:
    def test_vocabulary_lists_registry_names_only(self) -> None:
        vocabulary = registry_vocabulary()
        assert "visitors" in vocabulary
        assert "web_vital_lcp_p75" in vocabulary
        assert "country" in vocabulary
        assert "prefix" in vocabulary  # filter ops documented
        assert "SELECT" not in vocabulary  # vocabulary is names, never SQL


class TestCompile:
    async def test_valid_model_output_compiles(self) -> None:
        gateway = FakeGateway([GOOD])
        request = await compile_question(
            gateway, "org-1", question="quels pays ce mois-ci ?"  # type: ignore[arg-type]
        )
        assert request.metric == "visitors"
        assert request.dimensions == ["country"]
        # the model saw the registry vocabulary and the question
        prompt = json.dumps(gateway.conversations[0])
        assert "visitors" in prompt and "quels pays" in prompt

    async def test_markdown_fenced_json_is_tolerated(self) -> None:
        gateway = FakeGateway([f"```json\n{GOOD}\n```"])
        request = await compile_question(gateway, "org-1", question="pays ?")  # type: ignore[arg-type]
        assert request.metric == "visitors"

    async def test_invalid_output_gets_one_guided_repair_round(self) -> None:
        bad = json.dumps({"metric": "revenue_forecast", "period": {}})
        gateway = FakeGateway([bad, GOOD])
        request = await compile_question(gateway, "org-1", question="?")  # type: ignore[arg-type]
        assert request.metric == "visitors"
        # the repair round carried the validation error back to the model
        repair_prompt = json.dumps(gateway.conversations[1])
        assert "revenue_forecast" in repair_prompt or "unknown metric" in repair_prompt

    async def test_two_failures_raise_instead_of_guessing(self) -> None:
        gateway = FakeGateway(["not json at all", "still garbage"])
        with pytest.raises(AskCompilationError):
            await compile_question(gateway, "org-1", question="?")  # type: ignore[arg-type]


class TestAskEndpoint:
    async def test_disabled_ai_returns_503(self, api_client: httpx.AsyncClient) -> None:
        from tests.unit.conftest import login
        from tests.unit.test_auth_and_admin import create_org_chain

        owner = await login(api_client, "alice")
        org_id, _, _ = await create_org_chain(api_client, owner)
        response = await api_client.post(
            "/api/v1/ask",
            json={"question": "combien de visiteurs hier ?"},
            headers={**owner, "X-Oriflux-Org": org_id},
        )
        assert response.status_code == 503
        assert "AI" in response.json()["detail"]
