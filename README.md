# Oriflux

Self-hosted, multi-tenant analytics for the Sponge Theory ecosystem — web analytics +
product analytics + API analytics, cookieless / GDPR-first, real-time, AI on local SPT
Models. See `docs/PRD.md` (source of truth) and `CLAUDE.md`.

## Monorepo layout

| Path | What |
|---|---|
| `api/` | One Python package (`oriflux`), three entrypoints: **ingest**, **api**, **workers** — shared Pydantic models |
| `web/` | React dashboard (stub) |
| `sdk/js/` | `oriflux.js` web SDK (stub — served by ingest, no npm in V1) |
| `sdk/python/` | `oriflux-sdk` ASGI middleware (stub — MIT, public PyPI) |
| `deploy/` | Dev docker compose + (later) Swarm stack yml |

## Dev quickstart

```bash
cd deploy && docker compose up --build -d   # ClickHouse + PostgreSQL 16 + Redis + 3 services
# seed tenancy (Sponge Theory org + pilot projects) — prints the API keys ONCE
docker compose exec api python -m oriflux.bootstrap
# send a pageview (ingest keys are per source)
curl -s -X POST http://localhost:8100/api/v1/events \
  -H 'Authorization: Bearer ofx_ing_…' -H 'Content-Type: application/json' \
  -d '{"type":"pageview","url":"https://sponge-theory.ai/","referrer":""}'
# query it (read keys are org-wide; queries are scoped to the key's org)
curl -s -X POST http://localhost:8101/api/v1/query \
  -H 'Authorization: Bearer ofx_read_…' -H 'Content-Type: application/json' \
  -d '{"metric":"pageviews","period":{"start":"2026-07-01T00:00:00Z","end":"2026-08-01T00:00:00Z"}}'
```

## Tests

```bash
cd api
uv sync
uv run pytest tests/unit                       # no services needed
uv run pytest -m integration                   # needs deploy/ compose up
uv run mypy && uv run ruff check
```
