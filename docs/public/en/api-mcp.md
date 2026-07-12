# REST API & MCP

Everything the dashboard does goes through `/api/v1` — there is no private
API. Two read surfaces:

## REST — the typed query contract

`POST /api/v1/query` with a typed object:

```json
{
  "metric": "visitors",
  "dimensions": ["country"],
  "filters": [{"dimension": "project_id", "op": "eq", "value": "…"}],
  "granularity": "day",
  "period": {"start": "2026-06-01T00:00:00Z", "end": "2026-07-01T00:00:00Z"},
  "compare_to": "previous_period"
}
```

Metrics and dimensions are validated against a hand-maintained registry —
never free-form SQL. Authentication: an org read key (`ofx_read_…`,
`Authorization: Bearer` header).

## MCP — for your agents

The (read-only) MCP server is exposed at `/mcp` with the same read keys:
typed queries, funnels, retention, insights, alerts, annotations. See the
repository's `docs/mcp.md` for the tool-by-tool detail.
