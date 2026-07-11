"""Seam: explained alerts/anomalies (issue #36, PRD §6).

The decomposition is registry-only statistics; the LLM only phrases the
already-ranked contributors. Explanation failure never blocks anything.
"""

from datetime import UTC, datetime

from oriflux.ai.explain import explain_movement, rank_contributors

WINDOW = (datetime(2026, 7, 11, 8, tzinfo=UTC), datetime(2026, 7, 11, 9, tzinfo=UTC))


class DimExecutor:
    """country breakdown: ES collapsed, FR stable."""

    def __init__(self) -> None:
        self.sqls: list[str] = []

    def execute(self, sql, params):  # type: ignore[no-untyped-def]
        self.sqls.append(sql)
        if "country" in sql:
            return [{"country": "FR", "value": 90}, {"country": "ES", "value": 4}]
        return [{"page": "/docs", "value": 60}, {"page": "/", "value": 34}]


class FakeGateway:
    enabled = True

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def chat(self, org_id, *, feature, messages, temperature=0.2):  # type: ignore[no-untyped-def]
        import json

        self.prompts.append(json.dumps(messages))
        return "La baisse vient surtout de l'Espagne (4 vs 90 pour la France)."


class TestRankContributors:
    def test_contributors_come_from_registry_queries_only(self) -> None:
        executor = DimExecutor()
        contributors = rank_contributors(
            executor, org_id="o", project_id="p", metric="pageviews",
            window=WINDOW, dimensions=("country", "page"),
        )
        assert contributors["country"][0] == {"country": "FR", "value": 90}
        assert all("SELECT" in sql and "org_id" in sql for sql in executor.sqls)


class TestExplainMovement:
    async def test_explanation_cites_computed_contributors(self) -> None:
        gateway = FakeGateway()
        text = await explain_movement(
            gateway, DimExecutor(), org_id="o", project_id="p",
            metric="pageviews", window=WINDOW,
            headline="pageviews -62% (38 vs 100)",
        )
        assert "Espagne" in text
        assert "FR" in gateway.prompts[0]  # contributors were in the prompt

    async def test_gateway_failure_degrades_to_empty(self) -> None:
        class Broken:
            enabled = True

            async def chat(self, *a, **k):  # type: ignore[no-untyped-def]
                raise RuntimeError("down")

        text = await explain_movement(
            Broken(), DimExecutor(), org_id="o", project_id="p",
            metric="pageviews", window=WINDOW, headline="x",
        )
        assert text == ""
