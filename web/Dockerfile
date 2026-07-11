FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY scripts ./scripts
COPY src ./src
ARG VITE_GOOGLE_CLIENT_ID=""
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
RUN npm run build

FROM nginx:1.27-alpine
# templated config: the entrypoint envsubsts ${API_UPSTREAM} at startup
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV API_UPSTREAM=oriflux_api:8000
COPY --from=build /app/dist /usr/share/nginx/html
