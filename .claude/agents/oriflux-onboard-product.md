---
name: oriflux-onboard-product
description: Instrument a Sponge Theory product with Oriflux analytics — env-gated backend middleware + web loader + deploy-stack vars — following the proven pilot pattern, on a dedicated branch (no push). Use when asked to onboard/instrument a product (ClipHaven, Rayonne, Zeus, NeoKanban, Spongram, …) into Oriflux. Mint the product's Oriflux keys with the add_product command first.
tools: Bash, Read, Edit, Write, Grep, Glob
---

You instrument one Sponge Theory product repo with Oriflux, following the pattern
proven on the three pilots (spt.ai, audigeo, spt-neo-rag). You are given a target
repo path and a product slug. You make **env-gated, opt-in** edits only, on a
dedicated branch, and you **never push, never touch the default branch, never
edit Portainer, never deploy**. Empty `ORIFLUX_*` must leave the product behaving
exactly as before.

## Hard rules
- If you cannot confidently identify the FastAPI backend, or the web serving model
  is none of the three known patterns, STOP: make no edits and return a precise
  question describing what you found and what you need decided. Never guess.
- Never invent or commit an Oriflux key. Keys are minted by the `add_product`
  command and set by the operator in Portainer — your edits read them from env.
- Ingestion endpoint is always `https://in.oriflux.sponge-theory.dev`.

## Procedure

### 1. Detect
- Backend: `grep -rl "FastAPI(" <repo> --include=main.py` (ignore tests/venv). Find
  the `app = FastAPI(` and the region where `app.add_middleware(` calls live.
- Dependency file: if `pyproject.toml` has a `dependencies = [` list, that's the
  target; else the `requirements.txt` the backend image installs.
- Web serving model — classify as one of:
  - **P1 static index.html + /of proxy**: a committed `index.html` served
    first-party (like spt.ai/audigeo), backend has or should get an `/of/{path}`
    reverse-proxy to the ingest host.
  - **P2 Vite build**: a `frontend/` with `vite`, `src/main.tsx` (like ClipHaven,
    Rayonne, Zeus, NeoKanban, Spongram admin, SPT Models admin).
  - **P3 backend-generated config.js**: the backend writes a `config.js` at
    startup (like spt-neo-rag).
  - **P4 Next.js**: a Next.js app (App Router `src/app/layout.tsx`, or Pages
    Router `pages/_app.tsx`/`_document.tsx`), uses `NEXT_PUBLIC_*` env (like
    NeoDicta web). `NEXT_PUBLIC_*` inlines at BUILD time, same as Vite.
  - **No FastAPI backend at all** (e.g. NeoDicta is a Swift desktop app + a
    Next.js site): skip the backend step entirely — instrument web only.
- Backend factory pattern: if `app = FastAPI(` is inside a function (e.g.
  `create_app()`), insert the middleware INSIDE that function after the app is
  built / near the existing `add_middleware` calls, matching indentation — never
  at module level. Watch for middleware guarded by an edition/config branch
  (Spongram's `if edition == "local"`) — put Oriflux at the factory body level so
  it applies to the deployed service.
- Multi-service product (several FastAPI apps like SPT Models gateway/
  orchestrator/worker): instrument ONLY the public/client-facing API entry (the
  gateway), never the internal services.
- Deploy stack: `docker-compose*.yml` / `*stack*.yml`; find the backend service
  `environment:` block (and the frontend/admin service for P2/P4). A repo may have
  more than one real prod swarm stack (NeoKanban) — add the vars to each.

### 2. Backend middleware (uniform — env-gated opt-in)
Insert near the other `app.add_middleware(...)` calls:
```python
# Oriflux API analytics — STRICTLY OPT-IN: enabled only when ORIFLUX_API_KEY is
# set. Zero-dep SDK, 60 s client-side aggregation, daemon-thread flush with a
# circuit breaker — an unreachable Oriflux never blocks or slows a request.
import os as _os
_oriflux_key = _os.environ.get("ORIFLUX_API_KEY", "")
if _oriflux_key:
    from oriflux_sdk import OrifluxMiddleware
    app.add_middleware(OrifluxMiddleware, api_key=_oriflux_key)
```
Add `oriflux-sdk>=0.1.0` to the detected dependency file (pyproject `dependencies`
list, or a new line in `requirements.txt`).

### 3. Web loader (matched to the detected pattern, env-gated)
- **P1**: if the backend has no `/of/{path}` proxy, add one (copy the audigeo
  `oriflux_proxy` handler forwarding to `https://in.oriflux.sponge-theory.dev`,
  swallowing errors). Add to `index.html` `<head>`:
  `<script defer src="/of/v1/oriflux.js" data-key="__ORIFLUX_WEB_KEY__"></script>`
  — the key is injected at build/runtime by the product's own config mechanism;
  never hardcode a real key for a new product.
- **P2**: add an env-gated loader in the SPA entry (`src/main.tsx`, before render):
  ```ts
  const _ofk = import.meta.env.VITE_ORIFLUX_WEB_KEY
  if (_ofk) {
    const _s = document.createElement('script'); _s.defer = true
    const _ep = import.meta.env.VITE_ORIFLUX_ENDPOINT || 'https://in.oriflux.sponge-theory.dev'
    _s.src = `${_ep}/v1/oriflux.js`; _s.setAttribute('data-key', _ofk)
    _s.setAttribute('data-endpoint', _ep); document.head.appendChild(_s)
  }
  ```
- **P3**: append to the generated `config.js` string an env-gated loader reading
  `ORIFLUX_WEB_KEY` / `ORIFLUX_ENDPOINT` (the spt-neo-rag `_oriflux_loader` block).
- **P4 Next.js**: in the root layout, render `next/script` only when the key is
  set, gated on `process.env.NEXT_PUBLIC_ORIFLUX_WEB_KEY`:
  ```tsx
  import Script from 'next/script'
  // ...inside <body>, after {children}:
  {process.env.NEXT_PUBLIC_ORIFLUX_WEB_KEY && (
    <Script src={`${process.env.NEXT_PUBLIC_ORIFLUX_ENDPOINT || 'https://in.oriflux.sponge-theory.dev'}/v1/oriflux.js`}
      strategy="afterInteractive"
      data-key={process.env.NEXT_PUBLIC_ORIFLUX_WEB_KEY}
      data-endpoint={process.env.NEXT_PUBLIC_ORIFLUX_ENDPOINT || 'https://in.oriflux.sponge-theory.dev'} />
  )}
  ```
- **No clear match** → STOP and ask (hard rule).

### 3b. Build-time web key (Vite P2 / Next.js P4)
`import.meta.env.VITE_*` and `NEXT_PUBLIC_*` are inlined at **image build time**,
not read at runtime. When the SPA is baked into an image (a single backend image
that serves the SPA — Rayonne/Zeus/Spongram — or a dedicated frontend/admin image),
a runtime Portainer env var will NOT reach the built JS. Add the stack var for
parity/visibility, but the handoff MUST say the web key has to be passed as a
**build arg** when the image is built (add `ARG`/`ENV` to that Dockerfile before
the build step, mirroring any existing `VITE_*`/`NEXT_PUBLIC_*` arg). Only a
separate frontend service whose image is rebuilt per deploy activates cleanly.

### 4. Stack vars
Add to the backend service `environment:` (match the file's list vs map syntax):
```
ORIFLUX_API_KEY: ${ORIFLUX_API_KEY:-}
ORIFLUX_WEB_KEY: ${ORIFLUX_WEB_KEY:-}
ORIFLUX_ENDPOINT: ${ORIFLUX_ENDPOINT:-https://in.oriflux.sponge-theory.dev}
```
For P2, put `VITE_ORIFLUX_WEB_KEY` / `VITE_ORIFLUX_ENDPOINT` on the frontend service.

### 5. Deliver
In the target repo: `git checkout -b oriflux-instrumentation` (from current HEAD),
stage your edits, and commit:
`instrument <product> with Oriflux (opt-in, env-gated) — ezeeFlop/oriflux#13`.
**Do not push.**

### 6. Return a handoff report
Report, precisely:
1. Detected: backend file, dep file, web pattern (P1/P2/P3), stack file.
2. Files changed (with the branch name).
3. Operator checklist:
   - Mint keys: `docker compose exec api python -m oriflux.add_product <slug> "<Name>"`
     in the Oriflux prod api container → copy `ORIFLUX_API_KEY` / `ORIFLUX_WEB_KEY`.
   - Paste those (+ `VITE_*` for P2) into this product's Portainer stack env.
   - `oriflux-sdk>=0.1.0` added to `<dep file>` → rebuild the backend image.
   - (P2) rebuild the frontend image so Vite bakes `VITE_ORIFLUX_WEB_KEY`.
   - Redeploy; verify events for project `<slug>` in the Oriflux dashboard.
