"""Infra correlation (issue #29) — a live Zeus snapshot per project.

EXPLICITLY LISTED NON-REGISTRY SURFACE (like the live view): this reads
Zeus's native API, not ClickHouse — no analytics numbers flow through it.
Zeus has no per-service series API today, so this is a snapshot, not an
overlay (noted on the issue).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import Project, Role, User
from oriflux.integrations.zeus import ZeusClient

router = APIRouter(prefix="/api/v1", tags=["infra"])


class ZeusMappingIn(BaseModel):
    zeus_service: str | None = Field(default=None, max_length=128)


def _zeus(request: Request) -> ZeusClient | None:
    settings = request.app.state.settings
    if not settings.zeus_url or not settings.zeus_username:
        return None
    client = getattr(request.app.state, "zeus_client", None)
    if client is None:
        client = ZeusClient(
            settings.zeus_url,
            username=settings.zeus_username,
            password=settings.zeus_password,
        )
        request.app.state.zeus_client = client
    return client


@router.patch("/projects/{project_id}/zeus")
async def set_zeus_mapping(
    project_id: uuid.UUID,
    payload: ZeusMappingIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str | None]:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    await require_role(session, user, project.org_id, Role.admin)
    project.zeus_service = payload.zeus_service
    await session.commit()
    return {"zeus_service": project.zeus_service}


@router.get("/projects/{project_id}/infra")
async def project_infra(
    project_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    await require_role(session, user, project.org_id, Role.viewer)
    zeus = _zeus(request)
    if zeus is None or not project.zeus_service:
        return {"available": False}
    stats = await zeus.service_stats(project.zeus_service)
    if stats is None:
        return {"available": False}
    return {"available": True, "service": project.zeus_service, **stats}
