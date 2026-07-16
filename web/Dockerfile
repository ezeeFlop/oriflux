# Build context is the REPO ROOT (not web/): the in-app docs (#78) render the
# guides in ../docs/public, which live outside web/, so import.meta.glob needs
# them in the build context. Mirrors landing/Dockerfile.
FROM node:22-alpine AS build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/tsconfig.json web/vite.config.ts web/index.html ./
COPY web/scripts ./scripts
COPY web/src ./src
# The shared documentation source (single source, also served by the landing).
COPY docs/public /app/docs/public
ARG VITE_GOOGLE_CLIENT_ID=""
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
RUN npm run build

FROM nginx:1.27-alpine
# templated config: the entrypoint envsubsts ${API_UPSTREAM} at startup
COPY web/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV API_UPSTREAM=oriflux_api:8000
COPY --from=build /app/web/dist /usr/share/nginx/html
