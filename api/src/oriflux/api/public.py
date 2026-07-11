"""Public dashboards (issue #41): admin mints revocable share tokens; the
/public/{token} path serves an allow-listed metric subset with no auth,
noindex, and org isolation from the token's project."""

import asyncio
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import Project, Role, ShareToken, User
from oriflux.public.allowlist import is_public_query
from oriflux.query.engine import build_query
from oriflux.query.models import Filter, QueryRequest
from oriflux.security.keys import hash_api_key

router = APIRouter(tags=["public"])


class ShareOut(BaseModel):
    id: str
    token: str  # shown once
    public_path: str


@router.post("/api/v1/projects/{project_id}/share", status_code=201)
async def mint_share(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ShareOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="unknown project")
    await require_role(session, user, project.org_id, Role.admin)
    plaintext = f"ofx_pub_{secrets.token_urlsafe(24)}"
    token = ShareToken(
        org_id=project.org_id, project_id=project.id, token_hash=hash_api_key(plaintext)
    )
    session.add(token)
    await session.commit()
    return ShareOut(id=str(token.id), token=plaintext, public_path=f"/public/{plaintext}")


@router.delete("/api/v1/share/{share_id}", status_code=204)
async def revoke_share(
    share_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    token = await session.get(ShareToken, share_id)
    if token is None:
        raise HTTPException(status_code=404, detail="unknown share")
    await require_role(session, user, token.org_id, Role.admin)
    token.revoked_at = datetime.now(tz=UTC)
    await session.commit()


async def _resolve_token(session: AsyncSession, token: str) -> ShareToken:
    row = (
        await session.execute(
            select(ShareToken).where(ShareToken.token_hash == hash_api_key(token))
        )
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="invalid or revoked share link")
    return row


@router.post("/public/{token}/query")
async def public_query(
    token: str,
    request: QueryRequest,
    http_request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    response.headers["X-Robots-Tag"] = "noindex"
    share = await _resolve_token(session, token)
    if not is_public_query(request):
        raise HTTPException(status_code=403, detail="metric not available on public dashboards")
    request.filters.append(
        Filter(dimension="project_id", op="eq", value=str(share.project_id))
    )
    sql, params = build_query(request, org_id=str(share.org_id))
    executor = http_request.app.state.query_executor()
    results = await asyncio.to_thread(executor.execute, sql, params)
    return {"results": results, "metric": request.metric}
