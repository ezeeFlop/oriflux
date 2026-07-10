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
