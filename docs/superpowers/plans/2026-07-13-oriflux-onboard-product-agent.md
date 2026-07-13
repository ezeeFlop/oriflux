# Oriflux Onboard-Product Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a repeatable tool — a management command `add_product` plus a project-scoped subagent `oriflux-onboard-product` — that onboards a Sponge Theory product into Oriflux (mint keys, instrument the repo, hand off the Portainer vars), then use it to instrument ClipHaven, Rayonne, Zeus, NeoKanban and Spongram.

**Architecture:** The deterministic, security-sensitive minting lives in a tested Python command (`api/src/oriflux/add_product.py`) that reuses `bootstrap`'s org helper and `build_api_key`. The judgement-heavy repo instrumentation lives in a subagent (`.claude/agents/oriflux-onboard-product.md`) that auto-detects the backend + one of three web-serving patterns, applies env-gated edits on a dedicated branch, and refuses to guess when the model is unknown. Everything is env-gated (empty `ORIFLUX_*` = no-op), nothing is pushed, prod stays the operator's.

**Tech Stack:** Python 3.11+, SQLAlchemy 2 async, Pydantic v2, pytest (aiosqlite in-memory), uv; Claude Code subagent markdown.

## Global Constraints

- Python 3.11+, Pydantic v2, SQLAlchemy 2 async; `uv run mypy` and `uv run ruff check` must stay clean.
- Reuse, do not duplicate: `oriflux.bootstrap._get_or_create_org`, `oriflux.security.keys.build_api_key`, models `Organization/Project/Source/SourceType/ApiKey/KeyScope`.
- Ingestion endpoint literal: `https://in.oriflux.sponge-theory.dev`. SDK dependency literal: `oriflux-sdk>=0.1.0`.
- Instrumentation is **strictly opt-in / env-gated**: empty `ORIFLUX_*` ⇒ product behaves exactly as before (no script, no middleware).
- The subagent **never** pushes, **never** touches the target repo's default branch, **never** edits Portainer or deploys.
- Plaintext keys are shown once at mint; existing keys are not retrievable — say so, never fabricate.
- Command idempotent and safe to re-run.

---

### Task 1: `add_product` command + tests

**Files:**
- Create: `api/src/oriflux/add_product.py`
- Test: `api/tests/unit/test_add_product.py`

**Interfaces:**
- Consumes: `oriflux.bootstrap._get_or_create_org(session) -> Organization`; `oriflux.security.keys.build_api_key(*, org_id, scope, source_id=None, name="") -> tuple[ApiKey, str]`; models `Project(org_id, slug, name)`, `Source(project_id, type: SourceType, name)`, `SourceType.web|api`, `KeyScope.ingest`, `ApiKey.source_id|revoked_at`.
- Produces:
  - `@dataclass class ProductKeys: api_key: str | None; web_key: str | None` (None ⇒ source already had a non-revoked ingest key, plaintext not retrievable).
  - `async def ensure_product(session: AsyncSession, org: Organization, slug: str, name: str) -> ProductKeys`
  - `async def add_product(slug: str, name: str) -> None` (CLI entrypoint: migrations + engine + commit + print).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_add_product.py
"""Seam: onboarding a new product mints its project + web/api sources + ingest
keys idempotently (issue #13). Mirrors the bootstrap key-issuance contract."""

import pytest
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
                await session.execute(select(Source).where(Source.project_id == project.id))
            ).scalars().all()
            assert {s.type for s in sources} == {SourceType.web, SourceType.api}
            ingest = (
                await session.execute(
                    select(ApiKey).where(ApiKey.scope == KeyScope.ingest)
                )
            ).scalars().all()
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
                await session.execute(select(Project).where(Project.slug == "cliphaven"))
            ).scalars().all()
            assert len(projects) == 1
            ingest = (
                await session.execute(select(ApiKey).where(ApiKey.scope == KeyScope.ingest))
            ).scalars().all()
            assert len(ingest) == 2  # not 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && uv run pytest tests/unit/test_add_product.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'oriflux.add_product'`

- [ ] **Step 3: Write the implementation**

```python
# api/src/oriflux/add_product.py
"""Onboard one product into Oriflux: its project, web + api sources and one
ingest key per source. Idempotent — re-running mints nothing new (and cannot
re-show a key that already exists; plaintext is printed ONCE at creation).

    # dev
    uv run python -m oriflux.add_product cliphaven "ClipHaven"
    # prod (in the api container console — this is the operator's step)
    docker compose exec api python -m oriflux.add_product cliphaven "ClipHaven"

Prints the two keys in copy-paste form for the product's Portainer stack env:

    ORIFLUX_API_KEY=ofx_ing_...    # api source  → backend OrifluxMiddleware
    ORIFLUX_WEB_KEY=ofx_ing_...    # web source  → oriflux.js loader
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
        print("  (already onboarded — keys exist and cannot be re-shown; "
              "revoke + re-run to rotate)")
        return
    if keys.api_key:
        print(f"  ORIFLUX_API_KEY={keys.api_key}")
    if keys.web_key:
        print(f"  ORIFLUX_WEB_KEY={keys.web_key}")
    print(f"  ORIFLUX_ENDPOINT={INGEST_ENDPOINT}")
    print("  → paste these into the product's Portainer stack env, then redeploy.")


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && uv run pytest tests/unit/test_add_product.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Typecheck + lint**

Run: `cd api && uv run mypy && uv run ruff check`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
cd /Users/cve/GITHUB/spt/oriflux
git add api/src/oriflux/add_product.py api/tests/unit/test_add_product.py
git commit -m "feat: add_product command — mint a product's Oriflux project+sources+keys (#13)"
```

---

### Task 2: `oriflux-onboard-product` subagent

**Files:**
- Create: `.claude/agents/oriflux-onboard-product.md`

**Interfaces:**
- Consumes: the Task 1 command `python -m oriflux.add_product <slug> "<Name>"` (dev via `docker compose exec api …`).
- Produces: a dispatchable subagent type `oriflux-onboard-product` used in Task 3 and Task 4.

- [ ] **Step 1: Write the subagent file**

Create `.claude/agents/oriflux-onboard-product.md` with exactly this content:

````markdown
---
name: oriflux-onboard-product
description: Instrument a Sponge Theory product with Oriflux analytics — env-gated backend middleware + web loader + deploy-stack vars — following the proven pilot pattern, on a dedicated branch (no push). Use when asked to onboard/instrument a product (ClipHaven, Rayonne, Zeus, NeoKanban, Spongram, …) into Oriflux. Mint the product's Oriflux keys with the add_product command first.
tools: Bash, Read, Edit, Write, Grep, Glob
---

You instrument one Sponge Theory product repo with Oriflux, following the pattern
proven on the three pilots (spt.ai, audigeo, spt-neo-rag). You are given a target
repo path and a product slug. You make **env-gated, opt-in** edits only, on a
dedicated branch, and you **never push, never touch the default branch, never
edit Portainer, never deploy**. Empty `ORIFLUX_*` must leave the product behaving
exactly as before.

## Hard rules
- If you cannot confidently identify the FastAPI backend, or the web serving model
  is none of the three known patterns, STOP: make no edits and return a precise
  question describing what you found and what you need decided. Never guess.
- Never invent or commit an Oriflux key. Keys are minted by the `add_product`
  command and set by the operator in Portainer — your edits read them from env.
- Ingestion endpoint is always `https://in.oriflux.sponge-theory.dev`.

## Procedure

### 1. Detect
- Backend: `grep -rl "FastAPI(" <repo> --include=main.py` (ignore tests/venv). Find
  the `app = FastAPI(` and the region where `app.add_middleware(` calls live.
- Dependency file: if `pyproject.toml` has a `dependencies = [` list, that's the
  target; else the `requirements.txt` the backend image installs.
- Web serving model — classify as one of:
  - **P1 static index.html + /of proxy**: a committed `index.html` served
    first-party (like spt.ai/audigeo), backend has or should get an `/of/{path}`
    reverse-proxy to the ingest host.
  - **P2 Vite build**: a `frontend/` with `vite`, `src/main.tsx`, a separate
    frontend image and `VITE_*` env (like ClipHaven).
  - **P3 backend-generated config.js**: the backend writes a `config.js` at
    startup (like spt-neo-rag).
- Deploy stack: `docker-compose*.yml` / `*stack*.yml`; find the backend service
  `environment:` block (and the frontend service for P2).

### 2. Backend middleware (uniform — env-gated opt-in)
Insert near the other `app.add_middleware(...)` calls:
```python
# Oriflux API analytics — STRICTLY OPT-IN: enabled only when ORIFLUX_API_KEY is
# set. Zero-dep SDK, 60 s client-side aggregation, daemon-thread flush with a
# circuit breaker — an unreachable Oriflux never blocks or slows a request.
import os as _os
_oriflux_key = _os.environ.get("ORIFLUX_API_KEY", "")
if _oriflux_key:
    from oriflux_sdk import OrifluxMiddleware
    app.add_middleware(OrifluxMiddleware, api_key=_oriflux_key)
```
Add `oriflux-sdk>=0.1.0` to the detected dependency file (pyproject `dependencies`
list, or a new line in `requirements.txt`).

### 3. Web loader (matched to the detected pattern, env-gated)
- **P1**: if the backend has no `/of/{path}` proxy, add one (copy the audigeo
  `oriflux_proxy` handler forwarding to `https://in.oriflux.sponge-theory.dev`,
  swallowing errors). Add to `index.html` `<head>`:
  `<script defer src="/of/v1/oriflux.js" data-key="__ORIFLUX_WEB_KEY__"></script>`
  — the key is injected at build/runtime by the product's own config mechanism;
  never hardcode a real key for a new product.
- **P2**: add an env-gated loader in the SPA entry (`src/main.tsx`, before render):
  ```ts
  const _ofk = import.meta.env.VITE_ORIFLUX_WEB_KEY
  if (_ofk) {
    const _s = document.createElement('script'); _s.defer = true
    const _ep = import.meta.env.VITE_ORIFLUX_ENDPOINT || 'https://in.oriflux.sponge-theory.dev'
    _s.src = `${_ep}/v1/oriflux.js`; _s.setAttribute('data-key', _ofk)
    _s.setAttribute('data-endpoint', _ep); document.head.appendChild(_s)
  }
  ```
- **P3**: append to the generated `config.js` string an env-gated loader reading
  `ORIFLUX_WEB_KEY` / `ORIFLUX_ENDPOINT` (the spt-neo-rag `_oriflux_loader` block).
- **No clear match** → STOP and ask (hard rule).

### 4. Stack vars
Add to the backend service `environment:` (match the file's list vs map syntax):
```
ORIFLUX_API_KEY: ${ORIFLUX_API_KEY:-}
ORIFLUX_WEB_KEY: ${ORIFLUX_WEB_KEY:-}
ORIFLUX_ENDPOINT: ${ORIFLUX_ENDPOINT:-https://in.oriflux.sponge-theory.dev}
```
For P2, put `VITE_ORIFLUX_WEB_KEY` / `VITE_ORIFLUX_ENDPOINT` on the frontend service.

### 5. Deliver
In the target repo: `git checkout -b oriflux-instrumentation` (from current HEAD),
stage your edits, and commit:
`instrument <product> with Oriflux (opt-in, env-gated) — ezeeFlop/oriflux#13`.
**Do not push.**

### 6. Return a handoff report
Report, precisely:
1. Detected: backend file, dep file, web pattern (P1/P2/P3), stack file.
2. Files changed (with the branch name).
3. Operator checklist:
   - Mint keys: `docker compose exec api python -m oriflux.add_product <slug> "<Name>"`
     in the Oriflux prod api container → copy `ORIFLUX_API_KEY` / `ORIFLUX_WEB_KEY`.
   - Paste those (+ `VITE_*` for P2) into this product's Portainer stack env.
   - `oriflux-sdk>=0.1.0` added to `<dep file>` → rebuild the backend image.
   - (P2) rebuild the frontend image so Vite bakes `VITE_ORIFLUX_WEB_KEY`.
   - Redeploy; verify events for project `<slug>` in the Oriflux dashboard.
````

- [ ] **Step 2: Sanity-check the file parses as an agent (frontmatter present, tools listed)**

Run: `cd /Users/cve/GITHUB/spt/oriflux && head -5 .claude/agents/oriflux-onboard-product.md`
Expected: shows `---`, `name: oriflux-onboard-product`, `description:`, `tools: Bash, Read, Edit, Write, Grep, Glob`.

- [ ] **Step 3: Commit**

```bash
cd /Users/cve/GITHUB/spt/oriflux
git add .claude/agents/oriflux-onboard-product.md
git commit -m "feat: oriflux-onboard-product subagent — instrument a product repo (#13)"
```

---

### Task 3: Validate end-to-end against ClipHaven (reference, P2)

**Files:** none in this repo (produces a branch in `/Users/cve/GITHUB/spt/clipHaven`).

**Interfaces:** Consumes Task 1 command + Task 2 subagent.

- [ ] **Step 1: Dev-mint ClipHaven keys (proves the command in a live container)**

Run (compose stack up):
`cd /Users/cve/GITHUB/spt/oriflux/deploy && docker compose exec api python -m oriflux.add_product cliphaven "ClipHaven"`
Expected: prints `ORIFLUX_API_KEY=ofx_ing_…`, `ORIFLUX_WEB_KEY=ofx_ing_…`, `ORIFLUX_ENDPOINT=…`. Re-run → "already onboarded" (idempotent).

- [ ] **Step 2: Dispatch the subagent against ClipHaven**

Dispatch `oriflux-onboard-product` with prompt:
"Onboard ClipHaven. Target repo: /Users/cve/GITHUB/spt/clipHaven. Slug: cliphaven."
Expected: it detects backend `clipHaven/backend/app/main.py`, dep file
`clipHaven/backend/pyproject.toml` (or its requirements file), web pattern **P2**
(Vite, `frontend/src/main.tsx`), stack `clipHaven/docker/docker-compose.swarm.yml`;
creates branch `oriflux-instrumentation`, commits, does not push.

- [ ] **Step 3: Review the produced diff**

Run: `cd /Users/cve/GITHUB/spt/clipHaven && git log --oneline -1 && git show --stat HEAD`
Expected: one commit on `oriflux-instrumentation`; touches backend `main.py`
(middleware block), the dep file (`oriflux-sdk>=0.1.0`), `frontend/src/main.tsx`
(env-gated loader), the swarm stack (`ORIFLUX_*` + frontend `VITE_ORIFLUX_*`).
Verify empty-env = no-op (grep the middleware guard and the `if (_ofk)` guard).

- [ ] **Step 4: Report to the operator** the handoff checklist the subagent returned; do not push.

---

### Task 4: Roll out to the remaining products

**Files:** none here (produces `oriflux-instrumentation` branches in each product repo).

**Interfaces:** Consumes Task 1 + Task 2. One independent pass per product; a pass that hits an unknown web model STOPS and asks rather than guessing.

For each of `rayonne`, `zeus`, `spt-neo-kanban`, `spongram`:

- [ ] **Step 1: Dev-mint keys** — `docker compose exec api python -m oriflux.add_product <slug> "<Name>"` (slugs: `rayonne`/"Rayonne", `zeus`/"Zeus", `neokanban`/"NeoKanban", `spongram`/"Spongram" — confirm each display name against the repo's CLAUDE.md if unsure).
- [ ] **Step 2: Dispatch** `oriflux-onboard-product` with the repo path + slug.
- [ ] **Step 3: Review** the branch diff (`git show --stat` in the target repo); confirm env-gated guards and no push.
- [ ] **Step 4: Collect** each subagent's handoff checklist into one summary for the operator (per product: mint command, the `ORIFLUX_*`/`VITE_*` vars to paste, rebuild/redeploy notes).

Do not merge or push any product branch — the operator reviews and integrates.

---

## Self-review notes
- Spec coverage: add_product command (Task 1), subagent with 3 web patterns + detect + branch/no-push + handoff (Task 2), ClipHaven P2 validation (Task 3), rollout to the named products (Task 4). ✔
- Idempotency + no-reshow (spec §A) tested in Task 1 Step 1. ✔
- Env-gated / no-push / no-Portainer invariants encoded in the subagent hard rules and Global Constraints. ✔
- No placeholders: full command code, full agent body, exact commands/paths given. ✔
