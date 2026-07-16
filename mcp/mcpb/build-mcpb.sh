#!/usr/bin/env bash
# Build the Oriflux .mcpb bundle for Claude Desktop.
#
# Produces dist/oriflux-<version>.mcpb: the manifest + bridge entry +
# bundled mcp-remote proxy (Oriflux exposes the real MCP server remotely, so
# nothing product-specific is bundled). No secret is included — the base URL
# and read key are supplied by the user in Claude Desktop's extension config.
#
# Usage: ./build-mcpb.sh
set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(node -p "require('./manifest.json').version")"
BUNDLE_DIR="bundle"
OUT="oriflux-${VERSION}.mcpb"

echo "Building Oriflux MCPB v${VERSION}…"

# 1. install runtime deps (mcp-remote) into node_modules
npm install --omit=dev --no-audit --no-fund

# 2. stage a clean bundle: manifest + bridge + node_modules
rm -rf "$BUNDLE_DIR" && mkdir -p "$BUNDLE_DIR"
cp manifest.json index.mjs package.json "$BUNDLE_DIR/"
cp -R node_modules "$BUNDLE_DIR/node_modules"

# 3. validate the manifest, then pack (mcpb CLI from @anthropic-ai/mcpb).
#    The packed artifact is committed at the mcpb dir root (checked in, like the
#    other Sponge Theory .mcpb bundles); the repo root .gitignore ignores dist/.
npx --yes @anthropic-ai/mcpb@latest validate "$BUNDLE_DIR/manifest.json"
npx --yes @anthropic-ai/mcpb@latest pack "$BUNDLE_DIR" "$OUT"

rm -rf "$BUNDLE_DIR"
echo "Success: $OUT"
