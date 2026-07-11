"""Connector CRUD (issue #24) — admin-only; secrets are Fernet-encrypted at
rest and never returned. The webhook URL is shown at creation."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import Connector, ConnectorProvider, Project, Role, User
from oriflux.security.secrets import encrypt_secret

router = APIRouter(prefix="/api/v1", tags=["connectors"])


class ConnectorIn(BaseModel):
    provider: Literal["stripe", "lemonsqueezy"]
    webhook_secret: str = Field(min_length=8, max_length=256)


class ConnectorOut(BaseModel):
    id: str
    provider: str
    webhook_path: str


def _out(connector: Connector) -> ConnectorOut:
    return ConnectorOut(
        id=str(connector.id),
        provider=connector.provider,
        webhook_path=f"/api/v1/connectors/{connector.id}/webhook",
    )


@router.post("/projects/{project_id}/connectors", status_code=201)
async def create_connector(
    project_id: uuid.UUID,
    payload: ConnectorIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConnectorOut:
    settings = request.app.state.settings
    if not settings.fernet_key:
        raise HTTPException(status_code=503, detail="connectors disabled (no Fernet key)")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    await require_role(session, user, project.org_id, Role.admin)
    connector = Connector(
        org_id=project.org_id,
        project_id=project.id,
        provider=ConnectorProvider(payload.provider),
        webhook_secret_encrypted=encrypt_secret(payload.webhook_secret, settings.fernet_key),
    )
    session.add(connector)
    await session.commit()
    return _out(connector)


@router.get("/projects/{project_id}/connectors")
async def list_connectors(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ConnectorOut]:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    await require_role(session, user, project.org_id, Role.admin)
    rows = (
        await session.execute(select(Connector).where(Connector.project_id == project.id))
    ).scalars()
    return [_out(connector) for connector in rows]


@router.delete("/connectors/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    connector = await session.get(Connector, connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="unknown connector")
    await require_role(session, user, connector.org_id, Role.admin)
    await session.execute(delete(Connector).where(Connector.id == connector.id))
    await session.commit()
