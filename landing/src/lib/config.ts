// Every external URL is a build variable with a default. NEVER hardcode these
// in components — import from here so the Docker build can override any of them
// via ARG/ENV (PUBLIC_* is what Astro exposes to import.meta.env at build time).
export const SITE = import.meta.env.PUBLIC_SITE_URL ?? "https://oriflux.sponge-theory.dev";
export const APP_URL = import.meta.env.PUBLIC_APP_URL ?? "https://app.oriflux.sponge-theory.dev";
export const GITHUB_URL = import.meta.env.PUBLIC_GITHUB_URL ?? "https://github.com/ezeeFlop/oriflux";
export const INGEST_URL = import.meta.env.PUBLIC_INGEST_URL ?? "https://in.oriflux.sponge-theory.dev";
export const LIVE_DEMO_URL = import.meta.env.PUBLIC_LIVE_DEMO_URL ?? ""; // PublicView link, filled by slice #74
export const CONTACT_EMAIL = "contact@sponge-theory.io";
