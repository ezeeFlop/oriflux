"""FastAPI dependencies: DB session, current user (JWT), read-key org, RBAC."""

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.config import Settings
from oriflux.db.models import ApiKey, KeyScope, Membership, Role, User
from oriflux.security.keys import hash_api_key
from oriflux.security.tokens import InvalidToken, decode_access_token

bearer = HTTPBearer(auto_error=False)

_ROLE_ORDER = {Role.viewer: 0, Role.admin: 1, Role.owner: 2}


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user


async def require_role(
    session: AsyncSession, user: User, org_id: uuid.UUID, minimum: Role
) -> Membership:
    """403 unless `user` holds at least `minimum` in the organization."""
    membership = await session.get(Membership, (user.id, org_id))
    if membership is None or _ROLE_ORDER[membership.role] < _ROLE_ORDER[minimum]:
        raise HTTPException(status_code=403, detail="insufficient role")
    return membership


async def require_read_key_org(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Authenticate a read-scoped API key; returns the org_id that scopes
    every registry query (row-level isolation, PRD §8.3)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing API key")
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(credentials.credentials))
    )
    key = result.scalar_one_or_none()
    if key is None or key.revoked_at is not None:
        raise HTTPException(status_code=401, detail="invalid or revoked API key")
    if key.scope != KeyScope.read:
        raise HTTPException(status_code=403, detail="key lacks read scope")
    return str(key.org_id)


async def require_read_org(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Read access for the query surface, either caller (issue #7):

    - a read-scoped API key (org implied by the key), or
    - a dashboard JWT + `X-Oriflux-Org` header (membership checked,
      viewer is enough — reading is what viewers are for).
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing credentials")
    token = credentials.credentials
    if token.startswith("ofx_"):
        return await require_read_key_org(credentials, session)

    try:
        user_id = decode_access_token(token, settings)
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    org_header = request.headers.get("x-oriflux-org")
    if not org_header:
        raise HTTPException(status_code=400, detail="X-Oriflux-Org header required with a JWT")
    try:
        org_id = uuid.UUID(org_header)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-Oriflux-Org must be an org id") from exc
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    await require_role(session, user, org_id, Role.viewer)
    return str(org_id)
