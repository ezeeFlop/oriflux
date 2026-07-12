# ── Stage 1: build the static site ──────────────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app

# External URLs are baked at build time (Astro inlines PUBLIC_* into the HTML).
# Each has a sane default in src/lib/config.ts; override via --build-arg.
ARG PUBLIC_SITE_URL=https://oriflux.sponge-theory.dev
ARG PUBLIC_APP_URL=https://app.oriflux.sponge-theory.dev
ARG PUBLIC_GITHUB_URL=https://github.com/ezeeFlop/oriflux
ARG PUBLIC_INGEST_URL=https://in.oriflux.sponge-theory.dev
ARG PUBLIC_LIVE_DEMO_URL=

ENV PUBLIC_SITE_URL=$PUBLIC_SITE_URL \
    PUBLIC_APP_URL=$PUBLIC_APP_URL \
    PUBLIC_GITHUB_URL=$PUBLIC_GITHUB_URL \
    PUBLIC_INGEST_URL=$PUBLIC_INGEST_URL \
    PUBLIC_LIVE_DEMO_URL=$PUBLIC_LIVE_DEMO_URL

# The docs content lives OUTSIDE landing/ (../docs/public), so the build needs
# the repo checked in at the parent path. Build context must be the repo root:
#   docker build -f landing/Dockerfile -t oriflux-landing .
COPY landing/package.json landing/package-lock.json* ./landing/
WORKDIR /app/landing
RUN npm ci || npm install

COPY landing/ /app/landing/
COPY docs/public /app/docs/public
RUN npm run build

# ── Stage 2: serve with nginx ────────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY landing/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/landing/dist /usr/share/nginx/html
EXPOSE 80
