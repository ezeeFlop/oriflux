# oriflux-node

Oriflux API analytics for Node/Express (PRD §5.3) — the Apitally pattern:
requests aggregate client-side in 60 s windows keyed by (endpoint template,
method, status, consumer, caller IP), latencies land in log buckets, and one
tiny payload ships per window. The caller IP in the key is what makes API geo
possible: Oriflux resolves it to country/ASN at ingestion then discards it.

**SDK safety**: fire-and-forget by contract — 5 s send timeout, circuit
breaker after 3 consecutive failures (60 s cooldown), every code path wrapped.
Oriflux downtime can never impact your API. Overhead per request is O(1) map
work, well under 1 ms.

```ts
import express from "express";
import { orifluxMiddleware } from "oriflux-node";

const app = express();
app.use(
  orifluxMiddleware({
    apiKey: process.env.ORIFLUX_API_KEY!, // ofx_ing_… key of the API source
    // endpoint: "https://my.site/of",    // optional first-party proxy
    // consumer: (req) => req.auth?.tenantId ?? "",
  }),
);
```

Cardinality is capped at ~2 000 distinct keys per window; beyond that, new
callers collapse into an explicit overflow bucket with the IP dropped (their
geo shows as `unresolved` — the data stays honest about itself).

Publish: `npm publish` from this directory (human step, like PyPI for the
Python SDK).
