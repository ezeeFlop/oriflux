"""Idempotent bootstrap: the first organization, its projects, sources and
keys. Defaults seed the Sponge Theory org with the three pilot products
(PRD phase 1); self-hosters override everything through the environment
(issue #71) — same command, their own tenancy:

    uv run python -m oriflux.bootstrap            # dev
    docker compose exec api python -m oriflux.bootstrap   # containers

Environment overrides:
    ORIFLUX_BOOTSTRAP_ORG_SLUG      org slug        (default sponge-theory)
    ORIFLUX_BOOTSTRAP_ORG_NAME      org name        (default Sponge Theory)
    ORIFLUX_BOOTSTRAP_OWNER_EMAIL   owner login     (Google account email)
    ORIFLUX_BOOTSTRAP_PROJECTS      "slug:Name,slug:Name" (default: the pilots)
    ORIFLUX_BOOTSTRAP_APP_URL       dashboard URL printed at the end

Creates (only what's missing): the org, the owner user, web+api sources per
project, one ingest key per source and one org-wide read key. Plaintext keys
are printed ONCE at creation — store them; they are not retrievable afterwards.
"""

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.config import get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.db.migrate import run_migrations
from oriflux.db.models import (
    ApiKey,
    KeyScope,
    Membership,
    Organization,
    Project,
    Role,
    Source,
    SourceType,
    User,
)
from oriflux.security.keys import build_api_key

ORG_SLUG = os.environ.get("ORIFLUX_BOOTSTRAP_ORG_SLUG", "sponge-theory")
ORG_NAME = os.environ.get("ORIFLUX_BOOTSTRAP_ORG_NAME", "Sponge Theory")
_DEFAULT_PROJECTS = "sponge-theory-ai:sponge-theory.ai,audigeo:AudiGEO,neorag:NeoRAG"
PILOT_PROJECTS = [
    (entry.split(":", 1)[0].strip(), entry.split(":", 1)[-1].strip())
    for entry in os.environ.get("ORIFLUX_BOOTSTRAP_PROJECTS", _DEFAULT_PROJECTS).split(",")
    if entry.strip()
]
BOOTSTRAP_KEY_NAME = "bootstrap"


async def _get_or_create_org(session: AsyncSession) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.slug == ORG_SLUG))
    ).scalar_one_or_none()
    if org is None:
        org = Organization(slug=ORG_SLUG, name=ORG_NAME)
        session.add(org)
        await session.flush()
        print(f"created org {ORG_SLUG}")
    return org


async def _ensure_owner(session: AsyncSession, org: Organization) -> None:
    email = os.environ.get(
        "ORIFLUX_BOOTSTRAP_OWNER_EMAIL", "christophe.verdier@sponge-theory.io"
    )
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email)
        session.add(user)
        await session.flush()
    if await session.get(Membership, (user.id, org.id)) is None:
        session.add(Membership(user_id=user.id, org_id=org.id, role=Role.owner))
        print(f"granted owner to {email}")


async def _ensure_source_key(session: AsyncSession, org: Organization, source: Source) -> None:
    existing = (
        await session.execute(
            select(ApiKey).where(
                ApiKey.source_id == source.id,
                ApiKey.name == BOOTSTRAP_KEY_NAME,
                ApiKey.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    key, plaintext = build_api_key(
        org_id=org.id, scope=KeyScope.ingest, source_id=source.id, name=BOOTSTRAP_KEY_NAME
    )
    session.add(key)
    print(f"  ingest key [{source.name}]: {plaintext}")


async def _ensure_projects(session: AsyncSession, org: Organization) -> None:
    for slug, name in PILOT_PROJECTS:
        project = (
            await session.execute(
                select(Project).where(Project.org_id == org.id, Project.slug == slug)
            )
        ).scalar_one_or_none()
        if project is None:
            project = Project(org_id=org.id, slug=slug, name=name)
            session.add(project)
            await session.flush()
            print(f"created project {slug}")
        for source_type in (SourceType.web, SourceType.api):
            source = (
                await session.execute(
                    select(Source).where(
                        Source.project_id == project.id, Source.type == source_type
                    )
                )
            ).scalar_one_or_none()
            if source is None:
                source = Source(
                    project_id=project.id, type=source_type, name=f"{name} ({source_type})"
                )
                session.add(source)
                await session.flush()
            await _ensure_source_key(session, org, source)


async def _ensure_read_key(session: AsyncSession, org: Organization) -> None:
    existing = (
        await session.execute(
            select(ApiKey).where(
                ApiKey.org_id == org.id,
                ApiKey.scope == KeyScope.read,
                ApiKey.name == BOOTSTRAP_KEY_NAME,
                ApiKey.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    key, plaintext = build_api_key(org_id=org.id, scope=KeyScope.read, name=BOOTSTRAP_KEY_NAME)
    session.add(key)
    print(f"  read key [{ORG_SLUG}]: {plaintext}")


async def bootstrap() -> None:
    settings = get_settings()
    await asyncio.to_thread(run_migrations, settings)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        org = await _get_or_create_org(session)
        await _ensure_owner(session, org)
        await _ensure_projects(session, org)
        await _ensure_read_key(session, org)
        await session.commit()
    await engine.dispose()
    print("bootstrap complete (idempotent — safe to re-run)")
    app_url = os.environ.get("ORIFLUX_BOOTSTRAP_APP_URL")
    if app_url:
        owner = os.environ.get(
            "ORIFLUX_BOOTSTRAP_OWNER_EMAIL", "christophe.verdier@sponge-theory.io"
        )
        print(f"dashboard: {app_url} — sign in with Google as {owner}")


if __name__ == "__main__":
    sys.exit(asyncio.run(bootstrap()))
