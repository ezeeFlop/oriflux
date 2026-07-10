#!/bin/bash
# oriflux_workers (#16): uvicorn (healthz + Streams batchers) next to a
# Celery worker with embedded beat (GeoIP refresh, alert evaluation,
# phase-2 jobs). Single container; if either process dies the container
# exits so Swarm/compose restarts the pair.
set -e

celery -A oriflux.workers.celery_app worker --beat --loglevel INFO --concurrency 1 &
uvicorn oriflux.workers.main:app --host 0.0.0.0 --port 8000 &

wait -n
echo "workers: a process exited — stopping the container" >&2
exit 1
