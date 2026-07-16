import type { SourceType } from "./api";

/** Central ingest endpoint — the default baked into oriflux.js (PRD §5.1);
 *  products behind a first-party proxy override it with data-endpoint. */
export const INGEST_ENDPOINT = "https://in.oriflux.sponge-theory.dev";

/** Ready-to-paste integration snippet for a source — the 30-minute promise.
 *  App sources (custom events over HTTP) have no one-liner yet → null. */
export function integrationSnippet(type: SourceType, key: string): string | null {
  if (type === "web") {
    return `<script defer src="${INGEST_ENDPOINT}/v1/oriflux.js" data-key="${key}"></script>`;
  }
  if (type === "api") {
    return [
      "from oriflux_sdk import OrifluxMiddleware",
      "",
      `app.add_middleware(OrifluxMiddleware, api_key="${key}")`,
    ].join("\n");
  }
  return null;
}

/** Public read-only MCP endpoint for external agents (Claude Code / Desktop,
 *  any MCP client). Matches the plugin/MCPB userConfig default (docs/mcp.md). */
export const MCP_ENDPOINT = "https://api.oriflux.sponge-theory.dev/mcp";

/** The public Sponge Theory marketplace + the Oriflux plugin id. */
export const MCP_MARKETPLACE_REF = "ezeeFlop/claude-plugins";
export const MCP_PLUGIN_ID = "oriflux@sponge-theory";

/** Displayed in the mcpServers snippet where the user pastes their own key —
 *  never a real key (the panel doesn't have one; read keys are shown once). */
export const READ_KEY_PLACEHOLDER = "ofx_read_…";

/** One-click path: add the marketplace, then install the plugin (Claude Code). */
export const mcpPluginCommands = [
  `/plugin marketplace add ${MCP_MARKETPLACE_REF}`,
  `/plugin install ${MCP_PLUGIN_ID}`,
].join("\n");

/** Manual path for any MCP client (or Claude Desktop's custom connector):
 *  the raw mcpServers block, with the read key pasted in by the user. */
export function mcpServersConfig(key: string = READ_KEY_PLACEHOLDER): string {
  return JSON.stringify(
    {
      mcpServers: {
        oriflux: {
          type: "http",
          url: MCP_ENDPOINT,
          headers: { Authorization: `Bearer ${key}` },
        },
      },
    },
    null,
    2,
  );
}
