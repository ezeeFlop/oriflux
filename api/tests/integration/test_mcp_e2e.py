"""Issue #12 e2e: a real MCP client session over HTTP against the live
stack — connect with a read key, list tools, answer 'how is the product
doing this week?' via get_overview."""

from datetime import UTC, datetime, timedelta

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tests.integration.conftest import API_URL, Tenant

pytestmark = pytest.mark.integration

EXPECTED_TOOLS = {
    # MVP set (#12)
    "list_projects", "get_overview", "query_metrics", "get_geo_breakdown", "get_api_health",
    # phase 2/3 additions
    "query_funnel", "query_retention", "get_alerts", "get_insights", "annotate", "ask_oriflux",
}


class TestMcpSession:
    async def test_read_key_session_lists_and_calls_the_tools(self, tenant: Tenant) -> None:
        headers = {"Authorization": f"Bearer {tenant.read_key}"}
        async with streamablehttp_client(f"{API_URL}/mcp", headers=headers) as (
            read, write, _,
        ), ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == EXPECTED_TOOLS

            projects = await session.call_tool("list_projects", {})
            assert not projects.isError
            assert "it" in (projects.content[0].text or "")

            now = datetime.now(tz=UTC)
            overview = await session.call_tool(
                "get_overview",
                {
                    "project": "it",
                    "period": {
                        "start": (now - timedelta(days=7)).isoformat(),
                        "end": now.isoformat(),
                    },
                },
            )
            assert not overview.isError
            text = overview.content[0].text or ""
            assert "visitors" in text
            assert "api_requests" in text

    async def test_an_ingest_key_cannot_use_the_tools(self, tenant: Tenant) -> None:
        headers = {"Authorization": f"Bearer {tenant.ingest_key}"}
        async with streamablehttp_client(f"{API_URL}/mcp", headers=headers) as (
            read, write, _,
        ), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_projects", {})
            assert result.isError or "403" in (result.content[0].text or "")
