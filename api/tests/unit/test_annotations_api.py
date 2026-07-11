"""Seam: annotations CRUD over /api/v1 (issue #25) — RBAC + ingest-key path.

Annotations mark releases/campaigns/incidents on a project timeline.
Dashboards read them next to time series; deploy tooling posts them with
the project's ingest key (a write credential it already holds).
"""

import httpx
import pytest

from tests.unit.conftest import login
from tests.unit.test_auth_and_admin import create_org_chain

ANNOTATION = {"kind": "release", "text": "v1.4.0 deployed", "happened_at": "2026-07-05T14:00:00Z"}
WINDOW = {"start": "2026-07-01T00:00:00Z", "end": "2026-07-08T00:00:00Z"}


@pytest.fixture
async def project(api_client: httpx.AsyncClient) -> tuple[dict[str, str], str, str, str]:
    owner = await login(api_client, "alice")
    org_id, project_id, source_id = await create_org_chain(api_client, owner)
    issued = await api_client.post(
        f"/api/v1/sources/{source_id}/keys", json={"name": "ci"}, headers=owner
    )
    ingest_key = issued.json()["key"]
    return owner, org_id, project_id, ingest_key


class TestAnnotationCrud:
    async def test_admin_creates_lists_deletes(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str, str]
    ) -> None:
        owner, _, project_id, _ = project
        created = await api_client.post(
            f"/api/v1/projects/{project_id}/annotations", json=ANNOTATION, headers=owner
        )
        assert created.status_code == 201, created.text
        annotation_id = created.json()["id"]

        listed = await api_client.get(
            f"/api/v1/projects/{project_id}/annotations",
            params=WINDOW,
            headers={**owner, "X-Oriflux-Org": project[1]},
        )
        assert [a["id"] for a in listed.json()] == [annotation_id]
        assert listed.json()[0]["kind"] == "release"

        deleted = await api_client.delete(
            f"/api/v1/annotations/{annotation_id}", headers=owner
        )
        assert deleted.status_code == 204

    async def test_window_filters_annotations(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str, str]
    ) -> None:
        owner, _, project_id, _ = project
        await api_client.post(
            f"/api/v1/projects/{project_id}/annotations", json=ANNOTATION, headers=owner
        )
        outside = await api_client.get(
            f"/api/v1/projects/{project_id}/annotations",
            params={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
            headers={**owner, "X-Oriflux-Org": project[1]},
        )
        assert outside.json() == []

    async def test_ingest_key_of_the_project_can_annotate(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str, str]
    ) -> None:
        """deploy-portainer.sh posts release annotations with the key it has."""
        owner, _, project_id, ingest_key = project
        created = await api_client.post(
            f"/api/v1/projects/{project_id}/annotations",
            json={"kind": "release", "text": "ci deploy", "happened_at": "2026-07-05T15:00:00Z"},
            headers={"Authorization": f"Bearer {ingest_key}"},
        )
        assert created.status_code == 201, created.text

    async def test_unknown_kind_is_rejected(
        self, api_client: httpx.AsyncClient, project: tuple[dict[str, str], str, str, str]
    ) -> None:
        owner, _, project_id, _ = project
        response = await api_client.post(
            f"/api/v1/projects/{project_id}/annotations",
            json={**ANNOTATION, "kind": "party"},
            headers=owner,
        )
        assert response.status_code == 422
