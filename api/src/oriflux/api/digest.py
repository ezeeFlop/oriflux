"""Digest subscription self-service (issue #26): each member manages their
own cadence/language for an organization; DELETE = unsubscribe, honored
immediately (the send job only reads live subscriptions)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import DigestSubscription, Role, User

router = APIRouter(prefix="/api/v1", tags=["digest"])


class DigestPrefIn(BaseModel):
    cadence: Literal["weekly", "monthly"]
    language: Literal["fr", "en", "es"] = "fr"


class DigestPrefOut(BaseModel):
    cadence: str
    language: str


@router.put("/orgs/{org_id}/digest")
async def set_digest_pref(
    org_id: uuid.UUID,
    payload: DigestPrefIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DigestPrefOut:
    await require_role(session, user, org_id, Role.viewer)
    existing = (
        await session.execute(
            select(DigestSubscription).where(
                DigestSubscription.user_id == user.id,
                DigestSubscription.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = DigestSubscription(
            org_id=org_id, user_id=user.id, cadence=payload.cadence, language=payload.language
        )
        session.add(existing)
    else:
        existing.cadence = payload.cadence
        existing.language = payload.language
    await session.commit()
    return DigestPrefOut(cadence=existing.cadence, language=existing.language)


@router.get("/orgs/{org_id}/digest")
async def get_digest_pref(
    org_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DigestPrefOut:
    await require_role(session, user, org_id, Role.viewer)
    existing = (
        await session.execute(
            select(DigestSubscription).where(
                DigestSubscription.user_id == user.id,
                DigestSubscription.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="no digest subscription")
    return DigestPrefOut(cadence=existing.cadence, language=existing.language)


@router.delete("/orgs/{org_id}/digest", status_code=204)
async def unsubscribe(
    org_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    await require_role(session, user, org_id, Role.viewer)
    await session.execute(
        delete(DigestSubscription).where(
            DigestSubscription.user_id == user.id,
            DigestSubscription.org_id == org_id,
        )
    )
    await session.commit()
