# Oriflux — Claude Desktop extension (.mcpb)

Connects **Claude Desktop** to your own Oriflux instance's **read-only** MCP
endpoint (streamable HTTP at `<base_url>/mcp`), authenticated with a read-scoped
API key. Same analytics surface as the Claude Code plugin
(`../claude_code_plugin/`): `list_projects`, `get_overview`, `query_metrics`,
`get_geo_breakdown`, `get_api_health`.

## Why a bridge

The MCPB manifest spec (`manifest_version` 0.3) only supports **locally-executed**
servers (`server.type` of `node` / `python` / `binary`) — there is **no native
`http`/remote server type**. Oriflux already exposes the real MCP server
remotely, so this bundle ships no product logic: `index.mjs` forwards Claude
Desktop's local stdio MCP transport to the remote `/mcp` via the standard
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) proxy, adding the
`Authorization: Bearer <key>` header.

No secret is baked in. The base URL and read key are entered in Claude Desktop's
extension configuration (`user_config`, the key marked `sensitive`) and reach the
bridge as the `OFX_BASE_URL` / `OFX_API_KEY` env vars.

> Claude Desktop can also add Oriflux as a native **custom connector**
> (Settings → Connectors) pointing at `<base_url>/mcp` with an
> `Authorization: Bearer <key>` header — no bundle required. This `.mcpb` is the
> one-double-click install alternative.

## Build

```bash
./build-mcpb.sh          # installs mcp-remote, validates the manifest, packs dist/oriflux-<version>.mcpb
```

Requires Node ≥ 18. The pack + validate use `@anthropic-ai/mcpb` (fetched via
`npx`). Install the result by dragging `dist/oriflux-<version>.mcpb` into Claude
Desktop → Settings → Extensions, then enter your Oriflux base URL and
`ofx_read_…` key.

## Versioning

Keep `manifest.json` `version` in step with the Claude Code plugin version.
Claude Desktop users re-download and re-install to update (no auto-update).
