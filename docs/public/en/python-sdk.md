# oriflux-sdk — API analytics for Python

`pip install oriflux-sdk` (PyPI, MIT license).

```python
from oriflux_sdk import OrifluxMiddleware

app.add_middleware(
    OrifluxMiddleware,
    api_key="ofx_ing_…",          # the API source's ingest key
    endpoint="https://in.oriflux.sponge-theory.dev",  # default
)
```

## Guarantees

- **Zero host impact**: in-memory aggregation in 60 s windows (the
  Apitally pattern), fire-and-forget delivery with a circuit breaker — an
  Oriflux outage or a quota `429` never surfaces in your app.
- **< 1 ms** of overhead per request, bounded memory (~2,000 aggregation
  keys per window, overflow into a `geo=unresolved` bucket).
- **Privacy**: the caller's IP is part of the aggregation key, resolved to
  country/ASN at ingestion then discarded — it is never persisted.

## What you get

Volumes, latencies (p50/p95/p99), 4xx/5xx error rates, endpoints,
consumers, caller geography — per minute.
