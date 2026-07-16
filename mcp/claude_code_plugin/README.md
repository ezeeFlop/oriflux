# oriflux — Claude Code plugin

**Oriflux by Sponge Theory** — a self-hosted, cookieless, multi-tenant analytics
platform unifying **web analytics + product analytics + API analytics** —
brought into Claude Code as a **read-only** analytics surface.

The plugin is 100% static and carries **no secret**: it talks directly to your
Oriflux instance over authenticated streamable HTTP (`type: http`). Your instance
URL and read key are entered once, natively, when you enable the plugin.

## What it does

Exposes your Oriflux instance as read-only MCP tools — every tool is the same
REST endpoint the dashboard uses, compiled through Oriflux's typed metric
registry, so answers never drift from the UI:

- **`list_projects`** — the products/properties visible to your key's org.
- **`get_overview`** — visitors, pageviews, sessions, bounce rate, session
  duration, API requests, error rates, p95 for a project over a period.
- **`query_metrics`** — the typed query object (metric, dimensions, filters,
  granularity, period, compare_to); returns rows **and** the executed SQL.
- **`get_geo_breakdown`** — geographic distribution (country / region / city).
- **`get_api_health`** — request volume, 4xx/5xx rates, p50/p95/p99 latency,
  top endpoints.

Plus:

- **`oriflux` skill** — teaches Claude how and when to use those tools (identify
  the project, pick the right shaped tool vs. `query_metrics`, cite the numbers,
  read visitor totals as visit-days).
- **Slash commands** — `/oriflux:projects`, `/oriflux:overview <project> <period>`.

> Advanced tools (funnels, retention, insights, alerts, natural-language *Ask
> Oriflux*) are on the Oriflux roadmap and may not yet be available on a given
> instance. The plugin is built around the read-only analytics surface that is
> live today.

## Install (marketplace)

```bash
/plugin marketplace add ezeeFlop/claude-plugins
/plugin install oriflux@sponge-theory
```

When you enable the plugin, Claude Code prompts you (native configuration form)
for two values:

| Field | Notes |
|---|---|
| **Oriflux API base URL** | e.g. `https://api.oriflux.sponge-theory.dev` (or your self-host), without `/mcp`. Default provided — **override it if the hosted instance is not yet live or you self-host.** |
| **Oriflux read key** | A read-scoped `ofx_read_…` key, issued per organization in the Oriflux dashboard. Read keys can only query analytics — never write. Stored masked in your system keychain — never in the plugin or a settings file in plaintext. |

The MCP server then connects automatically with `Authorization: Bearer <your key>`.

> If you already had this marketplace registered, refresh it first so the new
> plugin is visible: `/plugin marketplace update sponge-theory`.
>
> If you installed from the CLI and the config form didn't appear, run
> `/plugin configure oriflux@sponge-theory`.

### Manual fallback (any Claude Code version)

If your Claude Code build doesn't render the configuration form, add the server
by hand:

```bash
claude mcp add --transport http oriflux https://api.oriflux.sponge-theory.dev/mcp \
  --header "Authorization: Bearer <your ofx_read_ key>"
```

(Dev instance: `http://localhost:8101/mcp`.)

## Security

No secret ships in this plugin. Your read key is entered via Claude Code's native
`userConfig` (marked `sensitive`, stored in the system keychain) and is sent only
to your own Oriflux instance over HTTPS. The key is read-scoped: it can query
analytics but cannot write.

## Support

- Documentation: <https://oriflux.sponge-theory.dev>
- Contact: support@sponge-theory.io
