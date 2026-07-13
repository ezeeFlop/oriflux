"""Seam: onboarding a new product mints its project + web/api sources + ingest
keys idempotently (issue #13). Mirrors the bootstrap key-issuance contract."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oriflux.add_product import ProductKeys, ensure_product
from oriflux.bootstrap import _get_or_create_org
from oriflux.db.models import ApiKey, KeyScope, Project, Source, SourceType


async def _run(factory: async_sessionmaker[AsyncSession], slug: str, name: str) -> ProductKeys:
    async with factory() as session:
        org = await _get_or_create_org(session)
        keys = await ensure_product(session, org, slug, name)
        await session.commit()
        return keys


class TestEnsureProduct:
    async def test_mints_project_two_sources_and_two_ingest_keys(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        keys = await _run(db_sessionmaker, "cliphaven", "ClipHaven")
        assert keys.api_key and keys.api_key.startswith("ofx_ing_")
        assert keys.web_key and keys.web_key.startswith("ofx_ing_")
        assert keys.api_key != keys.web_key
        async with db_sessionmaker() as session:
            project = (
                await session.execute(select(Project).where(Project.slug == "cliphaven"))
            ).scalar_one()
            sources = (
                (await session.execute(select(Source).where(Source.project_id == project.id)))
                .scalars()
                .all()
            )
            assert {s.type for s in sources} == {SourceType.web, SourceType.api}
            ingest = (
                (await session.execute(select(ApiKey).where(ApiKey.scope == KeyScope.ingest)))
                .scalars()
                .all()
            )
            assert len(ingest) == 2

    async def test_is_idempotent_and_does_not_reshow_existing_keys(
        self, db_sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        first = await _run(db_sessionmaker, "cliphaven", "ClipHaven")
        assert first.api_key and first.web_key
        second = await _run(db_sessionmaker, "cliphaven", "ClipHaven")
        # re-run mints nothing new: keys already exist, plaintext not retrievable
        assert second.api_key is None and second.web_key is None
        async with db_sessionmaker() as session:
            projects = (
                (await session.execute(select(Project).where(Project.slug == "cliphaven")))
                .scalars()
                .all()
            )
            assert len(projects) == 1
            ingest = (
                (await session.execute(select(ApiKey).where(ApiKey.scope == KeyScope.ingest)))
                .scalars()
                .all()
            )
            assert len(ingest) == 2  # not 4
