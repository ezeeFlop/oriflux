# Design — `oriflux-onboard-product` agent

_Date: 2026-07-13 · Status: approved (design) · Repo: ezeeFlop/oriflux_

## Goal

Automate, as far as safely possible, onboarding a new Sponge Theory product into
Oriflux: mint the Oriflux project + sources + ingestion keys, instrument the
target product repo (backend API analytics + web analytics + deploy stack vars)
following the proven pilot pattern, and leave the operator exactly one class of
manual work — pasting the `ORIFLUX_*` variables into that product's Portainer
stack env and redeploying.

This captures the tacit knowledge from instrumenting the three pilots
(`spt.ai`, `audigeo`, `spt-neo-rag`) into a repeatable tool so the remaining
products (ClipHaven, Rayonne, Zeus, NeoKanban, Spongram, …) can be added in
minutes.

## Non-goals

- **No deploy.** The agent never touches Portainer, never sets prod stack env,
  never redeploys. Prod key-minting and stack-var pasting are the operator's.
- **No push.** The agent commits to a dedicated branch in the target repo but
  never pushes, never opens a PR, never touches the target repo's default branch.
- Not a general "instrument anything" tool — it targets Sponge Theory products
  that are FastAPI-backend + (optionally) SPA-frontend, deployed via a swarm/
  compose stack, matching the pilot shape.

## Decisions (settled during brainstorming, 2026-07-13)

1. **Minting mechanism** → a dedicated management command `add_product`
   (not the admin REST API, which needs an owner JWT; not mutating
   `bootstrap.py`'s global list). The agent prepares/runs it; on prod the
   operator runs it in the api container console.
2. **Web loader** → the agent **auto-detects** the serving model among three
   known patterns and applies the matching env-gated loader; if none matches
   clearly it **stops and asks** rather than guessing. Backend + web done in one
   pass.
3. **Delivery** → the agent creates branch `oriflux-instrumentation` in the
   target repo, commits with a clear message, **does not push**.
4. **Naming** → agent `oriflux-onboard-product`, command `add_product`.
5. **SDK** → `oriflux-sdk` 0.1.0 is published on public PyPI; all three pilots
   declare `"oriflux-sdk>=0.1.0"` in their `pyproject.toml` `dependencies`. The
   backend dependency step self-completes by adding that line to the target
   repo's dependency file.

## Components

### A. Management command — `api/src/oriflux/add_product.py`

Modeled on `set_stripe_prices.py` / `bootstrap.py`; reuses
`oriflux.security.keys.build_api_key` and the existing async sessionmaker.

**Invocation**
```
python -m oriflux.add_product <slug> "<Display Name>"
```

**Behavior (idempotent — safe to re-run):**
1. Ensure the SPT org exists (reuse bootstrap's `_get_or_create_org`; same
   `ORIFLUX_BOOTSTRAP_ORG_SLUG` default `sponge-theory`).
2. Create the project `<slug>` under the org if missing (reuse the model used by
   `admin.create_project`).
3. Ensure a **web** source and an **api** source on the project.
4. Mint one `KeyScope.ingest` key per source via `build_api_key(..., scope=ingest,
   source_id=...)` if the source has no bootstrap key yet (reuse the
   `_ensure_source_key` idempotency check).
5. Print the two plaintext keys **once**, in copy-paste form:
   ```
   ORIFLUX_API_KEY=ofx_ing_...    # api source → backend middleware
   ORIFLUX_WEB_KEY=ofx_ing_...    # web source → oriflux.js loader
   ORIFLUX_ENDPOINT=https://in.oriflux.sponge-theory.dev
   ```
   Plaintext is shown only for freshly-minted keys (hashes are stored; existing
   keys can't be re-revealed — the command says so explicitly on re-run).

**Environments**
- Dev: agent runs `docker compose exec api python -m oriflux.add_product …` and
  self-verifies (project + 2 sources + 2 keys exist).
- Prod: agent emits the exact command for the operator to run in the prod api
  container console; minting on prod is the operator's step.

### B. Subagent — `.claude/agents/oriflux-onboard-product.md`

Project-scoped subagent. Tools: `Bash, Read, Edit, Write, Grep, Glob`.
Invoked e.g. `Agent(subagent_type: "oriflux-onboard-product",
prompt: "onboard clipHaven at /Users/cve/GITHUB/spt/clipHaven, slug cliphaven")`.

Because a subagent cannot pause mid-run to ask the user, its ambiguity rule is:
**on an unrecognized serving model or missing backend, it makes no edits and
returns a precise question / blocker report** for the parent to relay.

**Playbook (per target repo):**

1. **Detect**
   - Backend: locate the FastAPI app (`grep -rl "FastAPI(" **/main.py`), the
     `app = FastAPI(...)` / `app.add_middleware(` insertion region.
   - Dependency file: `pyproject.toml` `dependencies` list (pilot style) vs
     `requirements.txt`. Add `oriflux-sdk>=0.1.0` to whichever the repo uses.
   - Frontend serving model — one of:
     - **P1 static `index.html` + `/of/*` proxy** (spt.ai, audigeo): a committed
       static `index.html` served first-party, backend has/needs an `/of/{path}`
       reverse-proxy to `https://in.oriflux.sponge-theory.dev`.
     - **P2 Vite build** (ClipHaven): separate frontend image, `VITE_*` env, a
       `main.tsx` entry — inject an env-gated loader reading
       `import.meta.env.VITE_ORIFLUX_WEB_KEY`.
     - **P3 backend-generated `config.js`** (NeoRAG): backend writes a
       `config.js` at startup — append the env-gated loader snippet there.
   - Deploy stack: `docker-compose*.yml` / `*stack*.yml` — find the backend (and
     frontend, for P2) service `environment:` block.

2. **Backend instrumentation** (uniform — the NeoRAG opt-in patron):
   ```python
   # Oriflux API analytics — STRICTLY OPT-IN: enabled only when ORIFLUX_API_KEY
   # is set. Zero-dep SDK, 60 s client-side aggregation, daemon-thread flush with
   # circuit breaker — an unreachable Oriflux never blocks or slows a request.
   import os as _os
   _oriflux_key = _os.environ.get("ORIFLUX_API_KEY", "")
   if _oriflux_key:
       from oriflux_sdk import OrifluxMiddleware
       app.add_middleware(OrifluxMiddleware, api_key=_oriflux_key)
   ```
   Placed near the other `app.add_middleware(...)` calls. Add
   `oriflux-sdk>=0.1.0` to the dependency file.

3. **Web instrumentation** (matched to the detected pattern, env-gated):
   - **P1**: add the `/of/*` proxy to the backend if absent (copy the audigeo
     `oriflux_proxy` handler + `_ORIFLUX_INGEST`/`_ORIFLUX_FORWARDED_HEADERS`),
     and the `<script defer src="/of/v1/oriflux.js" data-key="…">` tag to
     `index.html`. Key is env/build-injected, never committed for new products.
   - **P2**: env-gated loader in the SPA entry:
     ```ts
     const k = import.meta.env.VITE_ORIFLUX_WEB_KEY
     if (k) {
       const s = document.createElement('script'); s.defer = true
       const ep = import.meta.env.VITE_ORIFLUX_ENDPOINT || 'https://in.oriflux.sponge-theory.dev'
       s.src = `${ep}/v1/oriflux.js`; s.setAttribute('data-key', k)
       s.setAttribute('data-endpoint', ep); document.head.appendChild(s)
     }
     ```
     Add `VITE_ORIFLUX_WEB_KEY` / `VITE_ORIFLUX_ENDPOINT` to the frontend service
     env in the stack (build-arg note: Vite bakes at build time; the agent flags
     this so the operator rebuilds the frontend image, not just re-envs it).
   - **P3**: append the NeoRAG `_oriflux_loader` snippet to the generated
     `config.js` block.
   - **No clear match** → stop, no edits, return the question.

4. **Stack vars**: add to the backend service `environment:` (compose list or map
   syntax as the file uses):
   ```
   ORIFLUX_API_KEY: ${ORIFLUX_API_KEY:-}
   ORIFLUX_WEB_KEY: ${ORIFLUX_WEB_KEY:-}
   ORIFLUX_ENDPOINT: ${ORIFLUX_ENDPOINT:-https://in.oriflux.sponge-theory.dev}
   ```
   (`:-` empty default = clean no-op until keys are set.) For P2, `VITE_*` go on
   the frontend service.

5. **Deliver**: in the target repo, create branch `oriflux-instrumentation`
   (from current HEAD), stage the edits, commit:
   `instrument <product> with Oriflux (opt-in, env-gated) — ezeeFlop/oriflux#13`.
   No push.

**Final output (handoff checklist):**
1. Run the prod mint command (exact string, incl. container name) → copy the two keys.
2. Paste `ORIFLUX_API_KEY` / `ORIFLUX_WEB_KEY` (+ `VITE_*` for P2) into the
   product's Portainer stack env.
3. `oriflux-sdk` dependency added to `<file>` — rebuild the backend image.
4. (P2) rebuild the frontend image so Vite bakes `VITE_ORIFLUX_WEB_KEY`.
5. Redeploy the stack.
6. Verify events land in the Oriflux dashboard for project `<slug>` (Web → Pages
   / API analytics).

## Data flow

```
operator ──"onboard <product>"──▶ subagent
subagent ──detect──▶ target repo (read)
subagent ──(dev) docker compose exec──▶ add_product ──▶ Oriflux DB (project+sources+keys)
subagent ──edit+commit (branch, no push)──▶ target repo
subagent ──handoff checklist──▶ operator
operator ──run prod mint + paste vars + redeploy──▶ Portainer  (manual, by design)
instrumented product ──events──▶ in.oriflux.sponge-theory.dev ──▶ Oriflux dashboard
```

## Error handling / safety

- Idempotent minting; re-run never duplicates or leaks (existing keys not re-shown).
- Env-gated everywhere: empty `ORIFLUX_*` = the product behaves exactly as before
  (no script loaded, no middleware) — zero risk if keys are never set.
- Subagent never guesses an unknown serving model, never pushes, never touches
  the default branch, never edits Portainer.
- Backend middleware is additive and fire-and-forget (circuit breaker in the SDK);
  Oriflux downtime cannot affect the instrumented product (hard constraint).

## Testing

- Unit: `api/tests/unit/test_add_product.py` — idempotency (re-run is a no-op),
  both sources created, both `ofx_ing_*` keys minted with correct scope/source,
  org reused. Mirrors existing `bootstrap`/admin key tests.
- Integration/validation: dry dev run of the subagent against `clipHaven` as the
  reference product (P2 Vite path), asserting branch + commit + expected diff and
  a green `add_product` dev mint.

## Open items

- ClipHaven frontend Vite env is build-time (baked); confirm the frontend image
  build pipeline reads `VITE_ORIFLUX_WEB_KEY` as a build arg — captured as a
  handoff note (operator rebuilds), not a blocker for the agent's edits.
