# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

`docs/PRD.md` (v1.1, 2026-07-10, in French) is the single source of truth for scope and architecture. The PRD was validated in a design-review session on 2026-07-10; decisions from that session are marked *[Décision 2026-07-10]* in the text and are settled — don't reopen them without the user asking.

Phase 1 (MVP) is implemented: walking skeleton (#1), Swarm stack + deploy tooling (#2 — final Portainer click is human-owned), multi-tenancy/auth (#3), ingest enrichment incl. the canonical crawler list seeded from AudiGEO (#4), oriflux.js served at `/v1/oriflux.js` (#5), the full metric/dimension registry with cookieless sessionization (#6), oriflux-sdk + api_minutely pipeline (#8 — PyPI upload awaits one human command), threshold alerting (#11 — evaluator is asyncio, not Celery yet, deviation noted on the issue), read-only MCP server at `/mcp` (#12, see docs/mcp.md), and the React dashboard (#7/#9/#10 — web/, "oriflamme" design system, FR/EN, all numbers through `/api/v1/query`). Remaining: #13 (instrument the pilots) gated on the #2 production deployment.

### Build / test / run

```bash
cd deploy && docker compose up --build -d   # ClickHouse + PG16 + Redis (host port 6380) + ingest:8100 / api:8101 / workers:8102 / web:8103
cd api
uv sync                                     # deps (uv-managed, py3.11+)
uv run pytest tests/unit                    # unit tests, no services needed
uv run pytest -m integration                # needs the compose stack up (skips otherwise)
uv run mypy && uv run ruff check            # strict typing + lint — keep both clean
cd ../web && npm install && npm run dev     # dashboard dev server (proxies /api → :8101)
cd ../sdk/python && uv run pytest           # oriflux-sdk (separate uv project)
```

Dev tenancy: `docker compose exec api python -m oriflux.bootstrap` seeds the Sponge Theory org + pilot projects and prints the API keys once (idempotent). Keys are `ofx_ing_*` (per source) / `ofx_read_*` (org-wide), stored as sha256 hashes in PostgreSQL.

## Repo layout (decided)

**Public monorepo** (public since 2026-07-12 — never commit a secret; anything sensitive goes to gitignored `deploy/.env` or the Portainer env, and a leaked secret gets *rotated*, not just removed): `api/` (one Python package, three entrypoints: ingest, api, workers — shared Pydantic models), `web/` (React dashboard), `sdk/js/`, `sdk/python/`, `landing/` (Astro landing + public docs), `deploy/` (stack yml + deploy-portainer.sh + self-host compose). `oriflux.js` is served by the ingest service at a versioned path (no npm in V1); the Python SDK ships to public PyPI as `oriflux-sdk` under MIT. The server is **AGPL-3.0** *[Décision 2026-07-12]* — `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` live at the root.

## What Oriflux is

A self-hosted, multi-tenant analytics platform for the Sponge Theory ecosystem (AudiGEO, ClipHaven, Rayonne, Spongram, NeoRAG, etc.), unifying three domains no market tool covers together: **web analytics + product analytics + API analytics**. Cookieless / GDPR-first by design, real-time, with an AI layer running exclusively on local SPT Models (no analytics data leaves the infrastructure). Internal-first (dogfooding) but built multi-tenant and billable from V1.

## Decided architecture (PRD §8 — do not re-litigate)

Four services plus stores, deployed as Docker Swarm stack `spt-oriflux` (services named `oriflux_{ingest,api,workers,web,clickhouse}`), Traefik/NPM in front, `/healthz` healthchecks:

- **oriflux_ingest** (FastAPI, stateless): Pydantic validation → enrichment (MaxMind GeoLite2 local, UA parsing, bot/AI-agent classification) → daily-rotating visitor hash → **Redis Streams** buffer (deliberately no Kafka). Delivery is **at-least-once**: every event gets a UUID at ingest, the batcher uses a consumer group and `XACK`s only after the ClickHouse insert commits, inserts dedup on the UUID; Redis runs AOF `everysec` (≤ 1 s loss on Redis crash is documented as accepted).
- **ClickHouse** (single node, from day one — the PG-first fallback was explicitly killed): `events` and `api_minutely` tables, MergeTree + materialized views, monthly partitions, 13-month raw TTL, 5-year aggregates. Micro-batched from Redis Streams every 1–5 s. Ops: pinned LTS version, `clickhouse-backup` → MinIO from day one.
- **PostgreSQL 16**: metadata only — orgs, users, RBAC memberships, projects, sources, API keys, alert rules, annotations, connectors, billing.
- **oriflux_api** (FastAPI): REST `/api/v1` (everything the dashboard does goes through it), **MCP server** (fastapi-mcp pattern, read-only scoped API keys), and the query engine. The "DSL" is deliberately **not a language**: one typed Pydantic query object (`metric, dimensions, filters, granularity, period, compare_to`) validated against a hand-maintained metric/dimension registry mapping names to vetted SQL fragments. It is the single contract for dashboard, REST, MCP, and (phase 3) Ask Oriflux — **never write bespoke SQL for a dashboard endpoint outside the registry**; non-registry surfaces (live view) must be explicitly listed. Live view is 10 s polling in V1; WebSocket arrives in phase 3 with the globe.
- **oriflux_workers** (Celery + Redis): anomaly detection, AI insights (SPT Models), email digests (Resend), Stripe/Lemon Squeezy webhooks, GeoIP refresh, uptime checks, MinIO exports.
- **oriflux_web** (React 18 + TypeScript + React Query + Tailwind): real-time dashboard, FR/EN/ES i18n from V1.

Stack conventions: Python 3.11+, Pydantic v2, SQLAlchemy 2 async, UV for Python tooling — aligned with all other Sponge Theory products.

**Never name a Python subpackage `mcp`** (e.g. `app/mcp/`) — with `uvicorn app.main:app` run from `/app`, it shadows the `mcp` PyPI package that fastapi-mcp depends on (caused a prod outage on spt.ai).

## Hard constraints (product-defining — violating these breaks the value proposition)

- **Privacy**: cookieless; unique visitor = `hash(daily_salt, project_id, ip, user_agent)` with the salt destroyed daily; IP resolved to geo/ASN at ingestion then discarded, never persisted; `identify()` accepts only pseudonymous IDs (PII rejected by validation); DNT/GPC honored; 100 % EU data residency; AI sees aggregates only. Accepted consequence: **retention and multi-day funnels are identified-users-only**; anonymous funnels are session/day-scoped and labeled as such in the UI. Never reintroduce a persistent anonymous ID (localStorage) — it would kill the no-consent-banner differentiator.
- **AI**: all inference through SPT Models (chat/embed/rerank), never a cloud LLM. Ask Oriflux compiles NL → a constrained internal DSL → ClickHouse; **never free-form generated SQL**. Every AI answer cites its numbers and the executed query.
- **SDK safety**: Oriflux downtime must never impact instrumented products — fire-and-forget, short timeouts, circuit breaker. API SDK aggregates client-side in 60 s windows (Apitally pattern), < 1 ms overhead per request; the **caller IP is part of the aggregation key** (that's how API geo works — ingest resolves then discards it), capped at ~2 000 distinct keys per window with an explicit `geo=unresolved` overflow bucket. Web script < 2 KB gzipped; **central ingest domain is the default** (one script tag = the 30-min integration promise), first-party `/of/*` proxy is an opt-in deployed only on marketing surfaces; the JS SDK takes an `endpoint` option from day one.
- **Footprint**: < 2 vCPU / 4 GB RAM at rest (excluding ClickHouse) — being light vs PostHog is a commercial argument.
- **Multi-tenancy from day one**: `org_id` everywhere, row-level isolation, scoped API keys, quotas present in the schema and enforced from V1 (Rayonne lesson: no never-enforced quotas).
- Webhooks (Stripe/Lemon Squeezy) idempotent from V1; SSRF protection on connectors/outbound webhooks; Fernet encryption for connector tokens; ingestion rate limiting per key and per IP.

## Explicit non-goals (PRD §2.2 — reject scope drift)

Infrastructure monitoring (that's **Zeus** — Oriflux reads its `/api/metrics`, doesn't replace it), session replay (V3+), A/B testing / feature flags, raw log management, full APM/tracing (OTLP ingestion hooks only, P2).

## Roadmap phases

1. **MVP (6–8 wks)**: web + API ingestion, geo, per-product dashboard + portfolio home, 10 s-polling live view, threshold alerts (Slack/email), JS SDK + ASGI FastAPI SDK, typed query engine + registry, read-only MCP, JWT/OAuth Google auth, multi-tenant RBAC, FR/EN i18n (scaffolding day one), UA-regex-only bot classification (`traffic_class` column from the first event). Explicitly cut from phase 1: WebSocket, ES locale, behavioral bot heuristics. First instrumented: sponge-theory.ai, AudiGEO, NeoRAG.
2. Product depth: custom events/identify, funnels/retention (identified-only), bot/AI-agent intelligence + AI-visibility dashboard, ES locale, Web Vitals, Stripe/LS connectors, Node SDK, Zeus integration.
3. Full AI layer: Ask Oriflux (NL→typed query object), daily insights feed, narrative digests, WebSocket + live globe, AudiGEO rewired as a consumer of Oriflux traffic classification.
4. Commercialization: self-serve onboarding, billing, public docs, server license AGPL-3.0 *[Décision 2026-07-12]* (the Python SDK is MIT on PyPI). Pricing: Free 0 € (100k evts/mo), Pro 19 €/mo (1M), Scale 79 €/mo (10M), annual = 2 months free, Enterprise = contact.

## Ecosystem boundary (decided 2026-07-10)

Oriflux is the source of truth for traffic classification (single crawler/AI-agent list, seeded from AudiGEO's) for **Sponge Theory properties only**. AudiGEO keeps its customer-facing Bot Analytics product and becomes an Oriflux API/MCP consumer in phase 3+; until then the two coexist deliberately. AudiGEO customer sites never move into Oriflux.

## Working conventions

- PRD and product-facing docs are written in French; UI is trilingual FR/EN/ES from V1 (AudiGEO i18n pattern — translate everything, including status enums).
- Reuse existing Sponge Theory patterns rather than inventing: Zeus `/api/metrics` middleware, ClipHaven auth (JWT + OAuth Google) and Resend email, Rayonne security hardening, cliphaven/neokanban multi-arch build + `deploy-portainer.sh` deployment.
- Open questions live in PRD §15 — only §15.5 (Oriflux trademark clearance INPI/EUIPO, human task) remains open; §15.1 license (AGPL-3.0), §15.2 AudiGEO inversion, §15.3 status pages (in Oriflux, post-lot) and §15.4 retention (13 mo raw / 5 y aggregates, global) are closed. Don't silently decide §15.5 in code.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `ezeeFlop/oriflux` (private), operated via the `gh` CLI;
external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels are used verbatim (`needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
