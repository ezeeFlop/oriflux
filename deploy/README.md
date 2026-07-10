# Oriflux — deployment

Two files matter here:

| File | Purpose |
|---|---|
| `docker-compose.yml` | **Dev** stack (`docker compose up --build -d`) — ClickHouse + PG16 + Redis + the three services on localhost:8100/8101/8102 |
| `docker-stack.yml` | **Production** Swarm stack (`oriflux`) for the Sponge Theory cluster, deployed via Portainer |

`deploy-portainer.sh` builds the single multi-arch image (amd64 + arm64), pushes it
to `registry.sponge-theory.dev/oriflux-api`, and triggers the Portainer stack
webhook (cliphaven/neokanban pattern).

## First deployment (one-time, manual)

1. **Data directories** — on the `/data` share (visible from the NODE==2 host):

   ```bash
   mkdir -p /data/oriflux/prod/{clickhouse,postgres,redis,minio,backups}
   ```

2. **Push the image**:

   ```bash
   ./deploy-portainer.sh --no-deploy
   ```

3. **Create the stack in Portainer** — name it exactly `oriflux` (Swarm prefixes
   service names with the stack name; `oriflux` yields the canonical
   `oriflux_{ingest,api,workers,clickhouse,…}` service names). Paste
   `docker-stack.yml` and set the required env vars:

   | Var | Value |
   |---|---|
   | `ORIFLUX_JWT_SECRET` | generate (`openssl rand -hex 32`) — dashboard JWT signing |
   | `CLICKHOUSE_PASSWORD` | generate |
   | `POSTGRES_PASSWORD` | generate |
   | `MINIO_SECRET_KEY` | generate |
   | `ORIFLUX_GOOGLE_CLIENT_ID` | Google OAuth client id (dashboard login; optional until web ships) |
   | `OPS_WEBHOOK_URL` | Slack/ntfy webhook for backup-failure alerts (optional but wanted from day 1) |

   Then seed tenancy (idempotent; prints the API keys **once** — store them):

   ```bash
   docker exec $(docker ps -q -f name=oriflux_api) python -m oriflux.bootstrap
   ```

4. **Webhook** — in the Portainer stack, enable the webhook and export it locally:

   ```bash
   export PORTAINER_WEBHOOK="https://portainer.sponge-theory.dev/api/stacks/webhooks/<uuid>"
   ```

   Subsequent deploys are just `./deploy-portainer.sh`.

5. **DNS / Traefik** — the stack routes `in.oriflux.sponge-theory.dev` (ingest) and
   `api.oriflux.sponge-theory.dev` (query API) through the external `webfacing`
   network (entrypoint `websecure`, resolver `letsencrypt`). Both hosts already
   resolve via the `*.sponge-theory.dev` wildcard. The PRD's target domain
   `in.oriflux.sponge-theory.ai` has **no DNS records yet** — once the `.ai` zone
   is populated, override `INGEST_HOST`/`API_HOST` in the stack env.

## Post-deploy verification

```bash
# health
curl -s https://in.oriflux.sponge-theory.dev/healthz
curl -s https://api.oriflux.sponge-theory.dev/healthz

# walking-skeleton demo end-to-end (keys printed by the bootstrap step)
curl -s -X POST https://in.oriflux.sponge-theory.dev/api/v1/events \
  -H "Authorization: Bearer ofx_ing_…" -H 'Content-Type: application/json' \
  -d '{"type":"pageview","url":"https://sponge-theory.ai/prod-check"}'
sleep 3
curl -s -X POST https://api.oriflux.sponge-theory.dev/api/v1/query \
  -H "Authorization: Bearer ofx_read_…" -H 'Content-Type: application/json' \
  -d "{\"metric\":\"pageviews\",\"period\":{\"start\":\"$(date -u -v-1d +%FT%TZ)\",\"end\":\"$(date -u -v+1d +%FT%TZ)\"}}"
```

**ClickHouse restart / durability check** (acceptance): note the pageviews count,
`docker service update --force oriflux_clickhouse`, wait healthy, re-run the query —
the count must be identical (data lives in `/data/oriflux/prod/clickhouse`).

## Backups

- **ClickHouse** — `oriflux_clickhouse-backup` runs `clickhouse-backup create_remote`
  daily to the in-stack MinIO (`oriflux-backups` bucket, path `clickhouse/`,
  14 remote backups kept). Restore: `clickhouse-backup restore_remote <name>`.
- **PostgreSQL** — `oriflux_postgres-backup` runs a daily `pg_dump -Fc` to
  `/data/oriflux/prod/backups`, 14-day retention.
- **Failure alerting** (Rayonne audit lesson) — both sidecars POST
  `{"text": "[oriflux] … backup FAILED …"}` to `OPS_WEBHOOK_URL` on failure and
  log `[…] FAILED` as fallback.

**Deliberate-failure drill** (acceptance): set a wrong `CLICKHOUSE_PASSWORD` on the
`clickhouse-backup` service only (`docker service update --env-add
CLICKHOUSE_PASSWORD=wrong oriflux_clickhouse-backup`), `docker service update
--env-add BACKUP_INTERVAL_ONCE=1` isn't needed — just watch the next cycle or
`docker service scale oriflux_clickhouse-backup=0 && … =1` to force an immediate run;
the webhook must receive the FAILED message. Revert the env afterwards. Same drill
works on `postgres-backup` with a wrong `POSTGRES_PASSWORD`.

## Footprint (NFR §11)

Resource limits in the stack cap the non-ClickHouse footprint at
3 × 0.5 vCPU / 512 MB (services) + Redis 512 MB + PG 512 MB + MinIO 512 MB +
sidecars 384 MB — under the 2 vCPU / 4 GB target at rest (reservations are far
lower; limits are ceilings). ClickHouse is capped separately at 1.5 vCPU / 2 GB.
