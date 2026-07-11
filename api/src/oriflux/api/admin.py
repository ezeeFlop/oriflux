"""Admin REST: organizations → projects → sources → API keys, RBAC-guarded.

Ingest keys are issued per source (PRD §5.1); read keys are org-wide (used
by the dashboard, MCP and external consumers). Plaintext keys appear once
in the issuance response and are never retrievable again.

Deferred from PRD §9 to later issues: admin-access audit log and strict
CORS (wired when the web dashboard exists and origins are known).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.api.deps import get_current_user, get_session, require_role
from oriflux.db.models import (
    ApiKey,
    KeyScope,
    Membership,
    Organization,
    Plan,
    Project,
    Role,
    Source,
    SourceType,
    User,
)
from oriflux.security.keys import build_api_key

router = APIRouter(prefix="/api/v1", tags=["admin"])


class OrgIn(BaseModel):
    slug: str
    name: str


class OrgOut(BaseModel):
    id: str
    slug: str
    name: str


class ProjectIn(BaseModel):
    slug: str
    name: str


class ProjectOut(BaseModel):
    id: str
    org_id: str
    slug: str
    name: str


class SourceIn(BaseModel):
    type: SourceType
    name: str


class SourceOut(BaseModel):
    id: str
    project_id: str
    type: SourceType
    name: str


class KeyIn(BaseModel):
    name: str = ""


class KeyOut(BaseModel):
    """Listing shape: the prefix identifies a key, the secret never reappears."""

    id: str
    scope: KeyScope
    name: str
    key_prefix: str
    source_id: str | None
    revoked: bool
    created_at: datetime


class IssuedKeyOut(BaseModel):
    id: str
    key: str  # plaintext — shown exactly once
    key_prefix: str
    scope: KeyScope
    name: str


class MemberIn(BaseModel):
    email: str
    role: Role


class MemberOut(BaseModel):
    user_id: str
    org_id: str
    role: Role


class MemberRow(BaseModel):
    user_id: str
    email: str
    name: str
    role: Role


@router.post("/orgs", status_code=201)
async def create_org(
    payload: OrgIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OrgOut:
    exists = (
        await session.execute(select(Organization).where(Organization.slug == payload.slug))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="slug already taken")
    org = Organization(slug=payload.slug, name=payload.name)
    session.add(org)
    await session.flush()
    session.add(Membership(user_id=user.id, org_id=org.id, role=Role.owner))
    await session.commit()
    return OrgOut(id=str(org.id), slug=org.slug, name=org.name)


@router.post("/orgs/{org_id}/projects", status_code=201)
async def create_project(
    org_id: uuid.UUID,
    payload: ProjectIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectOut:
    await require_role(session, user, org_id, Role.admin)
    project = Project(org_id=org_id, slug=payload.slug, name=payload.name)
    session.add(project)
    await session.commit()
    return ProjectOut(
        id=str(project.id), org_id=str(org_id), slug=project.slug, name=project.name
    )


@router.get("/orgs/{org_id}/projects")
async def list_org_projects(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectOut]:
    await require_role(session, user, org_id, Role.viewer)
    projects = (
        (
            await session.execute(
                select(Project).where(Project.org_id == org_id).order_by(Project.slug)
            )
        )
        .scalars()
        .all()
    )
    return [
        ProjectOut(id=str(p.id), org_id=str(org_id), slug=p.slug, name=p.name)
        for p in projects
    ]


@router.post("/projects/{project_id}/sources", status_code=201)
async def create_source(
    project_id: uuid.UUID,
    payload: SourceIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SourceOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    await require_role(session, user, project.org_id, Role.admin)
    source = Source(project_id=project_id, type=payload.type, name=payload.name)
    session.add(source)
    await session.commit()
    return SourceOut(
        id=str(source.id), project_id=str(project_id), type=source.type, name=source.name
    )


@router.get("/projects/{project_id}/sources")
async def list_project_sources(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SourceOut]:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    await require_role(session, user, project.org_id, Role.viewer)
    sources = (
        (
            await session.execute(
                select(Source).where(Source.project_id == project_id).order_by(Source.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        SourceOut(id=str(s.id), project_id=str(project_id), type=s.type, name=s.name)
        for s in sources
    ]


@router.get("/orgs/{org_id}/keys")
async def list_org_keys(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[KeyOut]:
    await require_role(session, user, org_id, Role.admin)
    keys = (
        (
            await session.execute(
                select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        KeyOut(
            id=str(k.id),
            scope=k.scope,
            name=k.name,
            key_prefix=k.key_prefix,
            source_id=str(k.source_id) if k.source_id is not None else None,
            revoked=k.revoked_at is not None,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.post("/sources/{source_id}/keys", status_code=201)
async def issue_ingest_key(
    source_id: uuid.UUID,
    payload: KeyIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> IssuedKeyOut:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    project = await session.get(Project, source.project_id)
    assert project is not None  # FK guarantees it
    await require_role(session, user, project.org_id, Role.admin)

    key, plaintext = build_api_key(
        org_id=project.org_id, scope=KeyScope.ingest, source_id=source_id, name=payload.name
    )
    session.add(key)
    await session.commit()
    return IssuedKeyOut(
        id=str(key.id),
        key=plaintext,
        key_prefix=key.key_prefix,
        scope=KeyScope.ingest,
        name=key.name,
    )


@router.post("/orgs/{org_id}/keys", status_code=201)
async def issue_read_key(
    org_id: uuid.UUID,
    payload: KeyIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> IssuedKeyOut:
    await require_role(session, user, org_id, Role.admin)
    key, plaintext = build_api_key(org_id=org_id, scope=KeyScope.read, name=payload.name)
    session.add(key)
    await session.commit()
    return IssuedKeyOut(
        id=str(key.id),
        key=plaintext,
        key_prefix=key.key_prefix,
        scope=KeyScope.read,
        name=key.name,
    )


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")
    await require_role(session, user, key.org_id, Role.admin)
    if key.revoked_at is None:
        key.revoked_at = datetime.now(tz=UTC)
        await session.commit()


class UsageOut(BaseModel):
    """Plan + this month's consumption (issue #61). pct is None on
    unlimited plans (or when no plan row matches — the gate fails open)."""

    plan_slug: str
    plan_name: str | None
    monthly_events: int | None
    used: int
    pct: float | None


@router.get("/orgs/{org_id}/usage")
async def org_usage(
    org_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UsageOut:
    await require_role(session, user, org_id, Role.viewer)
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org not found")
    plan = await session.get(Plan, org.plan_slug)
    month_key = f"oriflux:quota:{org_id}:{datetime.now(tz=UTC):%Y%m}"
    raw = await request.app.state.redis.get(month_key)
    used = int(raw) if raw is not None else 0
    limit = plan.monthly_events if plan is not None else None
    pct = round(used / limit * 100, 1) if limit else None
    return UsageOut(
        plan_slug=org.plan_slug,
        plan_name=plan.name if plan is not None else None,
        monthly_events=limit,
        used=used,
        pct=pct,
    )


@router.get("/orgs/{org_id}/members")
async def list_members(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MemberRow]:
    await require_role(session, user, org_id, Role.viewer)
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.org_id == org_id)
            .order_by(User.email)
        )
    ).all()
    return [
        MemberRow(user_id=str(u.id), email=u.email, name=u.name, role=m.role) for m, u in rows
    ]


@router.post("/orgs/{org_id}/members", status_code=201)
async def add_member(
    org_id: uuid.UUID,
    payload: MemberIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemberOut:
    actor = await require_role(session, user, org_id, Role.admin)
    member = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if member is None:
        # pre-provisioned account: linked to Google on the member's first login
        member = User(email=payload.email)
        session.add(member)
        await session.flush()
    membership = await session.get(Membership, (member.id, org_id))
    # Owner is not grantable/revocable by admins: an admin could otherwise
    # mint themselves owner or demote the actual owner.
    touches_owner = payload.role == Role.owner or (
        membership is not None and membership.role == Role.owner
    )
    if touches_owner and actor.role != Role.owner:
        raise HTTPException(status_code=403, detail="only an owner can manage the owner role")
    if membership is None:
        membership = Membership(user_id=member.id, org_id=org_id, role=payload.role)
        session.add(membership)
    else:
        membership.role = payload.role
    await session.commit()
    return MemberOut(user_id=str(member.id), org_id=str(org_id), role=membership.role)
