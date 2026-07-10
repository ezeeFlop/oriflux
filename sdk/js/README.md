# oriflux.js

Cookieless web SDK, < 2 KB gzipped (currently ~0.9 KB), no cookies, no storage
identifiers. **The canonical source lives in the ingest package** —
[`api/src/oriflux/ingest/static/oriflux.js`](../../api/src/oriflux/ingest/static/oriflux.js) —
because the ingest service serves it at a versioned path (no npm in V1, PRD §5.1).
This directory becomes the npm package when V2 revisits distribution.

## Usage

```html
<script defer
        src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
        data-key="ofx_ing_…"></script>
```

- `data-key` (required): the source's ingest API key.
- `data-endpoint` (optional): point a product at its own first-party `/of/*`
  proxy — the central ingest domain is the default (décision 2026-07-10).

Tracks pageviews and SPA navigations (history API + popstate); referrer, UTM
and screen resolution ride along; geo, device/os/browser, locale and the
daily-rotating visitor hash are derived server-side. Fire-and-forget: an
unreachable ingest never breaks or slows the host page. DNT/GPC are honored
server-side.
