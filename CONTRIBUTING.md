# Contributing to Oriflux

Thanks for your interest! Oriflux is developed in the open by
[Sponge Theory](https://sponge-theory.ai). Issues and pull requests are welcome.

## Ground rules

- The product source of truth is `docs/PRD.md` (in French). Architecture decisions
  marked *[Décision …]* are settled — open an issue before challenging one.
- The server is **AGPL-3.0** (see `LICENSE`); the Python SDK under `sdk/python/` is MIT.
  By contributing you agree your contributions are licensed under the same terms.
- Privacy constraints are product-defining and non-negotiable: cookieless visitors
  (daily rotating hash), IPs resolved then discarded, no persistent anonymous IDs,
  DNT/GPC honored. PRs that weaken these are declined.

## Repo layout

| Path | What |
|---|---|
| `api/` | One Python package (`oriflux`), three entrypoints: ingest, api, workers |
| `web/` | React 18 + TypeScript dashboard |
| `sdk/js/` | `oriflux.js` (served by ingest at `/v1/oriflux.js`) |
| `sdk/python/` | `oriflux-sdk` ASGI middleware (MIT, PyPI) |
| `landing/` | Public landing + docs site (Astro) |
| `deploy/` | Docker compose (dev), Swarm stack, self-host compose |

## Build & test

```bash
cd deploy && docker compose up --build -d   # ClickHouse + PostgreSQL 16 + Redis + services

cd api
uv sync
uv run pytest tests/unit          # fast, no services
uv run pytest -m integration      # needs the compose stack (skips otherwise)
uv run mypy && uv run ruff check  # keep both clean — CI-level requirement

cd ../web
npm install
npm test                          # vitest + testing-library
npm run build                     # includes the FR/EN/ES i18n parity check

cd ../sdk/python && uv run pytest
```

## Conventions

- Python 3.11+, Pydantic v2, SQLAlchemy 2 async, UV for tooling. Strict mypy + ruff.
- Every dashboard number goes through `POST /api/v1/query` and the typed
  metric/dimension registry — never write bespoke SQL for a dashboard endpoint.
- UI strings go through the i18n catalogs (`web/src/i18n/{fr,en,es}.json`),
  enums included; the three catalogs must stay at key parity.
- Tests exercise external behavior at the highest seam available, not internals.

## Reporting security issues

Please do **not** open a public issue — see [SECURITY.md](SECURITY.md).
