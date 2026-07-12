# Self-hosting

Oriflux installs on your own machine in minutes: public multi-arch images
(amd64 + arm64) on GHCR and a readable `docker-compose.yml` — no
`install.sh | sh`. The server is AGPL-3.0 licensed — what you deploy is
[code you can read](https://github.com/ezeeFlop/oriflux).

## Requirements

- Docker Engine ≥ 24 with the Compose plugin.
- A machine with **~4 vCPU / 8 GB RAM recommended, ClickHouse included** —
  that is the honest sizing for comfortable use. The four Oriflux services
  themselves fit in < 2 vCPU / 4 GB; ClickHouse takes the rest and idles
  around 1 GB. Below that (2 vCPU / 4 GB total), it works for small volumes.
- ~10 GB of disk to start (ClickHouse compresses events aggressively;
  expect on the order of 1 GB per 10M events).
- A (free) Google OAuth client for dashboard sign-in — see below.

## Install

```bash
mkdir oriflux && cd oriflux
curl -fsSLO https://raw.githubusercontent.com/ezeeFlop/oriflux/main/deploy/self-host/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/ezeeFlop/oriflux/main/deploy/self-host/.env.example -o .env
# Edit .env: three required secrets (openssl rand -hex 32),
# your Google client id, the owner email and your projects.
docker compose up -d
```

Every service ships a healthcheck; `docker compose ps` should show everything
`healthy` (ClickHouse takes ~30 s on first boot).

## Bootstrap — your first organization

```bash
docker compose exec api python -m oriflux.bootstrap
```

The command is **idempotent** (safe to re-run). It creates your organization,
your projects with their web + API sources, prints the ingest and read keys
**exactly once**, then the dashboard URL. Store those keys: the server only
keeps a sha256 fingerprint.

## Dashboard sign-in

The dashboard authenticates with Google Sign-In. Create an OAuth client
("Web application") at
[console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials),
add your dashboard URL to the authorized JavaScript origins, and set
`ORIFLUX_GOOGLE_CLIENT_ID` in `.env`. The Google account matching
`ORIFLUX_BOOTSTRAP_OWNER_EMAIL` owns the organization.

## Reverse proxy & TLS

The compose file exposes two HTTP ports: `8080` (dashboard, which proxies
`/api` itself) and `8100` (ingest — the target of the snippet and SDKs).
Put your TLS reverse proxy in front, for example with Caddy:

```
analytics.example.com {
    reverse_proxy localhost:8080
}
in.example.com {
    reverse_proxy localhost:8100
}
```

The snippet to paste on your sites then becomes:

```html
<script defer src="https://in.example.com/v1/oriflux.js" data-key="ofx_ing_…"></script>
```

(`oriflux.js` accepts `data-endpoint` if you prefer serving the script and
receiving events on different hosts.)

## Backups

- **PostgreSQL** (metadata: orgs, keys, alert rules): a daily `pg_dump` is
  enough — the database is tiny.
- **ClickHouse** (the events): use
  [clickhouse-backup](https://github.com/Altinity/clickhouse-backup) to an
  S3/MinIO target. That is the exact setup of our production stack (daily
  `create_remote`, 14 remote backups kept).
- **Redis** is only a buffer: AOF `everysec` is already enabled; worst case,
  one second of in-flight events is lost on a crash.

## Upgrading

Images are tagged by version **and** `latest`. In production, pin a version
in `.env` (`ORIFLUX_TAG=0.1.0`) and upgrade deliberately:

```bash
# 1. back up (see above)
# 2. bump ORIFLUX_TAG in .env, then:
docker compose pull && docker compose up -d
```

Schema migrations run automatically when the `api` service starts. Read the
release notes before any major-version jump.

## Data retention

Defaults: **13 months of raw events** (ClickHouse TTL, monthly partitions)
and **5 years of aggregates**. IP addresses are never persisted — resolved
to geography at ingestion, then discarded.
