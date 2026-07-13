"""Onboard one product into Oriflux: its project, web + api sources and one
ingest key per source. Idempotent — re-running mints nothing new (and cannot
re-show a key that already exists; plaintext is printed ONCE at creation).

    # dev
    uv run python -m oriflux.add_product cliphaven "ClipHaven"
    # prod (in the api container console — this is the operator's step)
    docker compose exec api python -m oriflux.add_product cliphaven "ClipHaven"

Prints the two keys in copy-paste form for the product's Portainer stack env:

    ORIFLUX_API_KEY=ofx_ing_...    # api source  -> backend OrifluxMiddleware
    ORIFLUX_WEB_KEY=ofx_ing_...    # web source  -> oriflux.js loader
    ORIFLUX_ENDPOINT=https://in.oriflux.sponge-theory.dev
"""

import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oriflux.bootstrap import _get_or_create_org
from oriflux.config import get_settings
from oriflux.db import create_engine, create_session_factory
from oriflux.db.migrate import run_migrations
from oriflux.db.models import (
    ApiKey,
    KeyScope,
    Organization,
    Project,
    Source,
    SourceType,
)
from oriflux.security.keys import build_api_key

INGEST_ENDPOINT = "https://in.oriflux.sponge-theory.dev"
ONBOARD_KEY_NAME = "onboard"


@dataclass
class ProductKeys:
    api_key: str | None
    web_key: str | None


async def _ensure_source(
    session: AsyncSession, project: Project, source_type: SourceType, name: str
) -> Source:
    source = (
        await session.execute(
            select(Source).where(
                Source.project_id == project.id, Source.type == source_type
            )
        )
    ).scalar_one_or_none()
    if source is None:
        source = Source(project_id=project.id, type=source_type, name=name)
        session.add(source)
        await session.flush()
    return source


async def _ensure_ingest_key(
    session: AsyncSession, org: Organization, source: Source
) -> str | None:
    """Mint an ingest key for the source if it has none. Returns the plaintext
    for a freshly-minted key, or None if a non-revoked key already exists
    (existing plaintext is not retrievable)."""
    existing = (
        await session.execute(
            select(ApiKey).where(
                ApiKey.source_id == source.id,
                ApiKey.scope == KeyScope.ingest,
                ApiKey.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    key, plaintext = build_api_key(
        org_id=org.id, scope=KeyScope.ingest, source_id=source.id, name=ONBOARD_KEY_NAME
    )
    session.add(key)
    return plaintext


async def ensure_product(
    session: AsyncSession, org: Organization, slug: str, name: str
) -> ProductKeys:
    project = (
        await session.execute(
            select(Project).where(Project.org_id == org.id, Project.slug == slug)
        )
    ).scalar_one_or_none()
    if project is None:
        project = Project(org_id=org.id, slug=slug, name=name)
        session.add(project)
        await session.flush()
    web = await _ensure_source(session, project, SourceType.web, f"{name} (web)")
    api = await _ensure_source(session, project, SourceType.api, f"{name} (api)")
    web_key = await _ensure_ingest_key(session, org, web)
    api_key = await _ensure_ingest_key(session, org, api)
    return ProductKeys(api_key=api_key, web_key=web_key)


def _print_keys(slug: str, keys: ProductKeys) -> None:
    print(f"\nproduct '{slug}' — Oriflux ingestion config:")
    if keys.api_key is None and keys.web_key is None:
        print(
            "  (already onboarded — keys exist and cannot be re-shown; "
            "revoke + re-run to rotate)"
        )
        return
    if keys.api_key:
        print(f"  ORIFLUX_API_KEY={keys.api_key}")
    if keys.web_key:
        print(f"  ORIFLUX_WEB_KEY={keys.web_key}")
    print(f"  ORIFLUX_ENDPOINT={INGEST_ENDPOINT}")
    print("  -> paste these into the product's Portainer stack env, then redeploy.")


async def add_product(slug: str, name: str) -> None:
    settings = get_settings()
    await asyncio.to_thread(run_migrations, settings)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        org = await _get_or_create_org(session)
        keys = await ensure_product(session, org, slug, name)
        await session.commit()
    await engine.dispose()
    _print_keys(slug, keys)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('usage: python -m oriflux.add_product <slug> "<Display Name>"', file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(add_product(sys.argv[1], sys.argv[2])))
