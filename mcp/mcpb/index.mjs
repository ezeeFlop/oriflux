#!/usr/bin/env node
// Oriflux MCPB bridge.
//
// MCPB (Claude Desktop) bundles only locally-executed servers — there is no
// native "http"/remote server type. Oriflux already exposes a full read-only
// streamable-HTTP MCP server at <base_url>/mcp, so this bridge does not
// reimplement any tool: it forwards the local stdio MCP transport to that
// remote endpoint via the standard `mcp-remote` proxy, adding the Bearer
// header. No secret is baked in — the URL and key arrive as env vars that
// Claude Desktop substitutes from the extension's user configuration.

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const base = (process.env.OFX_BASE_URL || "https://api.oriflux.sponge-theory.dev")
  .trim()
  .replace(/\/+$/, "");
const key = (process.env.OFX_API_KEY || "").trim();

if (!key) {
  process.stderr.write(
    "oriflux: no API key configured. Set the Oriflux read key (ofx_read_…) " +
      "in the extension configuration.\n",
  );
  process.exit(1);
}

const url = `${base}/mcp`;
const proxy = join(here, "node_modules", "mcp-remote", "dist", "proxy.js");

// mcp-remote parses `--header "Name: value"` (splits on the first colon and
// trims the space), so the composed value is passed as a single argv element.
const args = [proxy, url, "--header", `Authorization: Bearer ${key}`];

const child = spawn(process.execPath, args, { stdio: "inherit" });
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});
