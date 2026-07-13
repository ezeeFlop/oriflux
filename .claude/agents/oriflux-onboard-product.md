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
  - **P2 Vite build**: a `frontend/` with `vite`, `src/main.tsx`, a separate
    frontend image and `VITE_*` env (like ClipHaven).
  - **P3 backend-generated config.js**: the backend writes a `config.js` at
    startup (like spt-neo-rag).
- Deploy stack: `docker-compose*.yml` / `*stack*.yml`; find the backend service
  `environment:` block (and the frontend service for P2).

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
- **No clear match** → STOP and ask (hard rule).

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
