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

### Connect in one click

The dashboard gathers everything under *Org settings → Connect to Claude*:
the endpoint, the key, and the paste-ready commands.

- **Claude Code** — add the public marketplace, then install the plugin:

  ```
  /plugin marketplace add ezeeFlop/claude-plugins
  /plugin install oriflux@sponge-theory
  ```

  At install time, enter the base URL (defaults to
  `https://api.oriflux.sponge-theory.dev`) and your `ofx_read_…` read key.
  Already installed? `/plugin marketplace update sponge-theory` first.

- **Claude Desktop** — double-click the `.mcpb` bundle (`mcp/mcpb/` in the
  repo), or add a custom connector pointing at `<base>/mcp` with the
  `Authorization: Bearer` header.

- **Any other MCP client** — the raw `mcpServers` config:

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

No secret is baked in: the URL and key stay yours, entered at configuration
time and sent only to your own instance.
