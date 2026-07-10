"""Dashboard auth: Google OAuth id_token → JWT (ClipHaven pattern)."""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, get_settings_dep
from oriflux.config import Settings
from oriflux.db.models import Membership, User
from oriflux.security.google import GoogleVerificationError
from oriflux.security.tokens import create_access_token

router = APIRouter(prefix="/api/v1", tags=["auth"])


class GoogleLoginIn(BaseModel):
    id_token: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrgMembershipOut(BaseModel):
    org_id: str
    role: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    orgs: list[OrgMembershipOut]


@router.post("/auth/google")
async def login_google(
    payload: GoogleLoginIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> TokenOut:
    try:
        # google-auth fetches Google's certs synchronously — keep it off the loop
        identity = await asyncio.to_thread(request.app.state.google_verifier, payload.id_token)
    except GoogleVerificationError as exc:
        raise HTTPException(status_code=401, detail="google verification failed") from exc

    user = (
        await session.execute(select(User).where(User.google_sub == identity.sub))
    ).scalar_one_or_none()
    if user is None:
        # link a pre-provisioned account (e.g. added as member by email) or create one
        user = (
            await session.execute(select(User).where(User.email == identity.email))
        ).scalar_one_or_none()
        if user is None:
            user = User(email=identity.email, name=identity.name)
            session.add(user)
        user.google_sub = identity.sub
        await session.commit()

    return TokenOut(access_token=create_access_token(user.id, settings))


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    memberships = (
        (await session.execute(select(Membership).where(Membership.user_id == user.id)))
        .scalars()
        .all()
    )
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        orgs=[OrgMembershipOut(org_id=str(m.org_id), role=m.role.value) for m in memberships],
    )
