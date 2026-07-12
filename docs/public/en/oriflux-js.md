# oriflux.js — web collection

A script under 2 KB gzipped, served by the ingest service at a versioned
path. No cookie, no identifier in localStorage: the unique visitor is a
daily hash (see [privacy](privacy.md)).

## Integration

```html
<script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
        data-key="ofx_ing_…"></script>
```

## Attributes

| Attribute | Role |
|---|---|
| `data-key` | **Required.** The source's ingest key (issued by the UI, shown once). |
| `data-endpoint` | Optional. Alternative ingest endpoint — used for the first-party `/of/*` proxy on marketing surfaces. |

## What is collected

Page views (URL, referrer, UTM), Web Vitals, custom events
(`window.oriflux.track(name, props)`), pseudonymous identification
(`window.oriflux.identify(pseudoId)` — any identifier that looks like an
email or a phone number is rejected at validation).

DNT and GPC are honored: the request receives `{"tracked": false}`.
