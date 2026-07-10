# oriflux-sdk

API analytics middleware for [Oriflux](https://sponge-theory.ai) — zero
dependencies, MIT-licensed, < 1 ms per request.

```bash
pip install oriflux-sdk
```

```python
from oriflux_sdk import OrifluxMiddleware

app.add_middleware(OrifluxMiddleware, api_key="ofx_ing_…")  # FastAPI / Starlette / any ASGI
```

That's the whole integration. The middleware aggregates client-side in 60 s
windows (Apitally pattern): request counts, error counts, latency histograms
and payload sizes keyed by templated endpoint, method, status code, consumer
and caller IP — the IP is what lets Oriflux resolve caller geography at
ingestion (then discard it; it is never stored). Cardinality is capped at
~2 000 keys per window with an explicit overflow bucket.

**Your API is never impacted**: recording is in-memory dict arithmetic,
flushing happens on a daemon thread with a 3 s timeout, failures are dropped
(never retried, never raised), and a circuit breaker pauses flushing entirely
while Oriflux is unreachable.

## Options

| Option | Default | Purpose |
|---|---|---|
| `api_key` | — (required) | the source's ingest key |
| `endpoint` | `https://in.oriflux.sponge-theory.dev` | self-hosted / first-party proxy target |
| `consumer` | `None` | `callable(scope) -> str` to attribute traffic to an API consumer |
| `flush_interval_s` | `60` | aggregation window |
| `max_keys` | `2000` | cardinality cap per window |
