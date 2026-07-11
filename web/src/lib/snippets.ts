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
