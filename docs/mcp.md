# Oriflux MCP server

Oriflux exposes a **read-only MCP server** (PRD §7.1) at `/mcp` on the api
service — HTTP-streamable, fastapi-mcp pattern. Every tool is the same REST
endpoint the dashboard uses, compiled through the metric/dimension registry:
answers can never drift from the UI.

## Auth

A **read-scoped API key** (`ofx_read_…`) sent as a Bearer header. Ingest keys
and revoked keys are rejected. Keys are issued per organization
(`POST /api/v1/orgs/{org_id}/keys`) or by `python -m oriflux.bootstrap`.

## Claude Code / Desktop configuration

```json
{
  "mcpServers": {
    "oriflux": {
      "type": "http",
      "url": "https://api.oriflux.sponge-theory.dev/mcp",
      "headers": { "Authorization": "Bearer ofx_read_…" }
    }
  }
}
```

(Dev: `http://localhost:8101/mcp`.)

## Ecosystem: traffic classification (§15.2)

Oriflux is the single source of truth for the crawler / AI-agent list for
Sponge Theory properties. Consumers (AudiGEO) read it instead of embedding
their own:

- `GET /api/v1/classification/crawlers` (read key) — the canonical list,
  versioned with an `ETag`; send `If-None-Match` to get `304` when unchanged.
- `POST /api/v1/classification/classify` `{"user_agent": ...}` → `{traffic_class, reason}`
  (the same `refine_traffic` path the ingest uses; reason is `ua:<Crawler>` or `heuristic:<name>`).

**AudiGEO integration (its repo):** replace the embedded `BOT_PATTERNS`
with a cached consumer of `/crawlers` (respect the ETag; keep the last
good copy as a fallback when Oriflux is unreachable). AudiGEO customer
sites never move into Oriflux; only the LIST source becomes shared.

## Tool inventory (phase 3 additions)

| Tool | Input | Notes |
|---|---|---|
| `query_funnel` | typed funnel (2-8 event/page steps, scope `session`\|`identified`, window, segment) | anonymous scope caps at 24 h by design |
| `query_retention` | activation event slug + `week`\|`month` + period | identified users only, by design |
| `get_insights` | org id (+limit) | daily feed: numbers + grounded prose + the query object |
| `get_alerts` | org id | firing/resolved alert events |
| `ask_oriflux` | a natural-language question (FR/EN/ES) | compiles to the typed query — never SQL; answers cite the executed query; 503 when AI is unconfigured, 429 past the org budget |
| `annotate` | project id + kind + text + timestamp | **the one write operation** — requires the project's *ingest* key; read keys get 403, so a read-only agent stays read-only |

Agent example: « mark this release » → `annotate(project, "release", "v2.1", now)`;
« why did signups move this week? » → `ask_oriflux` then `get_insights`.

## Tool inventory (phase 1 — read-only)

| Tool | Input | Returns |
|---|---|---|
| `list_projects` | — | projects (products) visible to the key's org |
| `get_overview` | `project` (slug), `period {start,end}` | visitors*, pageviews, sessions, bounce_rate, session_duration, api_requests, error rates, p95 |
| `query_metrics` | the typed query object (`metric, dimensions, filters, granularity, period, compare_to`) — **identical schema to `POST /api/v1/query`** | rows + the executed SQL (auditability) |
| `get_geo_breakdown` | `project`, `level` (country/region/city), `period`, `metric` | geo distribution, sorted |
| `get_api_health` | `project`, `period` | requests, 4xx/5xx rates, p50/p95/p99, top endpoints |

\* multi-day visitor totals are **visit-days** (daily rotating hash, PRD §9) —
the tools say so in their responses.

Validation errors list the available metric/dimension names, so agents can
self-repair a bad `query_metrics` call.

`annotate`, `get_insights` and `get_alerts` arrive in phase 3 (PRD roadmap).
