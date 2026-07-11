"""Annotations CRUD (PRD §5.3, issue #25).

Admins manage annotations from the dashboard; the project's ingest key —
a write credential deploy tooling already holds — may also POST one, so
`deploy-portainer.sh` can mark releases without a human token. Reads ride
require_read_org like every chart query.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_read_org, require_role
from oriflux.db.models import (
    Annotation,
    AnnotationKind,
    ApiKey,
    KeyScope,
    Project,
    Role,
    Source,
    User,
)
from oriflux.security.keys import hash_api_key

router = APIRouter(prefix="/api/v1", tags=["annotations"])
_bearer = HTTPBearer(auto_error=False)


class AnnotationIn(BaseModel):
    kind: AnnotationKind
    text: str = Field(min_length=1, max_length=512)
    happened_at: datetime


class AnnotationOut(BaseModel):
    id: str
    kind: AnnotationKind
    text: str
    happened_at: datetime


def _out(annotation: Annotation) -> AnnotationOut:
    return AnnotationOut(
        id=str(annotation.id),
        kind=annotation.kind,
        text=annotation.text,
        happened_at=annotation.happened_at,
    )


async def _project_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    return project


async def _authorize_writer(
    request: Request,
    session: AsyncSession,
    project: Project,
    credentials: HTTPAuthorizationCredentials | None,
) -> None:
    """JWT admin on the org, or an ingest key of one of the project's sources."""
    if credentials is not None and credentials.credentials.startswith("ofx_"):
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(credentials.credentials))
        )
        key = result.scalar_one_or_none()
        if key is None or key.revoked_at is not None or key.scope != KeyScope.ingest:
            raise HTTPException(status_code=401, detail="invalid or revoked API key")
        source = await session.get(Source, key.source_id) if key.source_id else None
        if source is None or source.project_id != project.id:
            raise HTTPException(status_code=403, detail="key does not belong to this project")
        return
    user = await get_current_user(credentials, session, request.app.state.settings)
    await require_role(session, user, project.org_id, Role.admin)


@router.post("/projects/{project_id}/annotations", status_code=201,
             operation_id="annotate",
             summary="Mark a release/campaign/incident on the project timeline")
async def create_annotation(
    project_id: uuid.UUID,
    payload: AnnotationIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AnnotationOut:
    project = await _project_or_404(session, project_id)
    await _authorize_writer(request, session, project, credentials)
    annotation = Annotation(
        org_id=project.org_id,
        project_id=project.id,
        kind=payload.kind,
        text=payload.text,
        happened_at=payload.happened_at,
    )
    session.add(annotation)
    await session.commit()
    return _out(annotation)


@router.get("/projects/{project_id}/annotations")
async def list_annotations(
    project_id: uuid.UUID,
    start: datetime,
    end: datetime,
    org_id: str = Depends(require_read_org),
    session: AsyncSession = Depends(get_session),
) -> list[AnnotationOut]:
    project = await _project_or_404(session, project_id)
    if str(project.org_id) != org_id:
        raise HTTPException(status_code=403, detail="project outside your organization")
    rows = (
        await session.execute(
            select(Annotation)
            .where(
                Annotation.project_id == project.id,
                Annotation.happened_at >= start,
                Annotation.happened_at < end,
            )
            .order_by(Annotation.happened_at)
        )
    ).scalars()
    return [_out(annotation) for annotation in rows]


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    annotation = await session.get(Annotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="unknown annotation")
    await require_role(session, user, annotation.org_id, Role.admin)
    await session.execute(delete(Annotation).where(Annotation.id == annotation.id))
    await session.commit()
