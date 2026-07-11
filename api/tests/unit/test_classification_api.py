"""Seam: Oriflux as the single source of truth for the crawler list
(issue #42, PRD §15.2). Consumers (AudiGEO) read this; UA in → class out."""

import httpx
import pytest

from tests.unit.conftest import login
from tests.unit.test_auth_and_admin import create_org_chain


@pytest.fixture
async def read_headers(api_client: httpx.AsyncClient) -> dict[str, str]:
    owner = await login(api_client, "alice")
    _, _, source_id = await create_org_chain(api_client, owner)
    # a read key for the org
    org = await api_client.get("/api/v1/me", headers=owner)
    org_id = org.json()["orgs"][0]["org_id"]
    key = await api_client.post(
        f"/api/v1/orgs/{org_id}/keys", json={"name": "reader"}, headers=owner
    )
    return {"Authorization": f"Bearer {key.json()['key']}"}


class TestCrawlerList:
    async def test_canonical_list_with_etag(
        self, api_client: httpx.AsyncClient, read_headers: dict[str, str]
    ) -> None:
        response = await api_client.get("/api/v1/classification/crawlers", headers=read_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["version"]
        names = {c["name"] for c in body["crawlers"]}
        assert "GPTBot" in names and "Googlebot" in names
        assert any(c["class"] == "ai_agent" for c in body["crawlers"])
        etag = response.headers["etag"]

        cached = await api_client.get(
            "/api/v1/classification/crawlers",
            headers={**read_headers, "If-None-Match": etag},
        )
        assert cached.status_code == 304

    async def test_classify_a_user_agent(
        self, api_client: httpx.AsyncClient, read_headers: dict[str, str]
    ) -> None:
        response = await api_client.post(
            "/api/v1/classification/classify",
            json={"user_agent": "Mozilla/5.0 (compatible; GPTBot/1.1)"},
            headers=read_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["traffic_class"] == "ai_agent"
        assert body["reason"] == "ua:GPTBot"

    async def test_requires_a_read_key(self, api_client: httpx.AsyncClient) -> None:
        response = await api_client.get("/api/v1/classification/crawlers")
        assert response.status_code == 401
