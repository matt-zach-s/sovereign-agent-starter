# Integrations UI scaffold — design

**Date:** 2026-06-18
**Status:** Approved (brainstorm), pending implementation plan
**Repo:** byoc-agent-starter

## 1. Problem & goal

The BYOC Agent Starter ships a self-hosted chatbot + tiny Ollama model into a
customer's own cloud (sovereign: no frontier API calls, everything in-VPC). It
already declares a **Tier-1 integration seam** (`src/app/integrations/` with
`openapi_tools.py` + `mcp_tools.py` stubs reading `OPENAPI_SPEC_URLS` /
`MCP_SERVER_URLS`), but the **only** way to add an integration today is: fork →
edit Python → set env vars → redeploy. There is no UI.

**Goal:** add a minimal, *teachable* web UI that lets an enterprise operator wire
in an internal HTTP system (via its OpenAPI spec) **without editing code**, with
all reasoning, action, and credentials staying inside the customer's boundary.

This is explicitly **not** an attempt to out-feature Open WebUI / Dify. The
example app is a forkable reference; its value is the legible seam + the Nuon BYOC
harness, not a product-grade integrations console. (See positioning note in
project memory: market Nuon's deploy/operate/scale-across-customers story, not the
chatbot.)

## 2. Research basis (why OpenAPI-by-URL, not OAuth-to-SaaS)

Deep research across Claude/MCP, OpenAI GPT Actions, Dify, Open WebUI, Flowise,
LibreChat, n8n, VS Code MCP, and the dev frameworks found two camps:

- **SaaS-reach-in** (Claude.ai connectors, ChatGPT GPT Actions): the vendor cloud
  calls the integration *outbound*; **requires a public-internet-reachable
  target.** Wrong fit for air-gapped/private-network systems. (The notion that
  private networks are handled by "allowlist the vendor's IPs so SaaS reaches in"
  was explicitly refuted.)
- **Agent-runs-inside-the-network** (self-hosted clients): converged on the same
  ~6-field registration pattern — name/description, an **OpenAPI spec (URL or
  paste)** or MCP server URL, a base-URL override, **auth = None / API-key header
  / Bearer**, a server-side secret, an enable toggle + test-connection, then the
  spec **expands into per-operation tools**.

This design copies that converged on-prem pattern.

## 3. Locked decisions (scope)

| Decision | Choice |
|---|---|
| Functional depth | **Working OpenAPI path end-to-end**; MCP stays a clearly-marked "coming next" tab (stub unchanged). |
| Persistence / write-back | **ConfigMap (defs) + K8s Secret (auth) are the source of truth**, pre-seeded via Nuon/Helm/GitOps. The app **never writes to the cluster**. UI is read + **live-add into the running process**; to persist, it **emits ConfigMap+Secret YAML** to apply. |
| UI surface | **Separate `/integrations` page** (`static/integrations.html`), single-column registry + **modal** add. Mirrors the existing one-file vanilla chat page. |
| Operations → tools | **Operator selects a subset** of operations (checklist). Only selected ops enter the model's tool array (small models degrade past ~8 tools). |
| Auth types (v1) | **None / Bearer / API-key header** only. (Basic, mTLS = documented future.) |
| Secrets | Stored in the **K8s Secret**, injected **server-side at call time**; defs reference by `secret_ref`; **never returned to the browser**. |
| Chat state | **Stateless backend + client-side localStorage** (see §8). |
| Process | Brainstorm → spec → plan → implement. |

**Out of scope (YAGNI):** MCP dispatch, OAuth, Basic/mTLS, write-back-to-cluster,
multi-user/RBAC, server-side chat history, any datastore.

## 4. Architecture & module layout

`src/app/integrations/` becomes small, single-purpose, independently-testable
modules. `main.py` shrinks toward thin (mount router + run tool-call loop).

| Module | One job | Depends on |
|---|---|---|
| `integrations/config.py` | Load integration **defs** from the mounted ConfigMap YAML (`INTEGRATIONS_CONFIG`, default `/etc/chatbot/integrations.yaml`) + **secret values** from the mounted Secret dir (`INTEGRATIONS_SECRETS_DIR`, default `/etc/chatbot/secrets`). Boot-time registry seed. | stdlib, PyYAML |
| `integrations/registry.py` | In-memory list of `Integration` (config-loaded **and** session-added); enable/disable; derive the `TOOLS` array from enabled + selected operations. | config, openapi_tools |
| `integrations/openapi_tools.py` | Parse a spec (URL or pasted JSON/YAML) → enumerate operations → emit OpenAI tool defs for **selected** operations (name=`operationId`, or a stable name derived from `method`+`path` when the spec omits it; params from JSON-Schema). *(Fleshes out existing stub.)* | httpx, PyYAML |
| `integrations/dispatch.py` | Execute one tool call: `operationId` + args → HTTP request to `base_url`+path (path/query/body), inject auth from the secret store, call in-VPC endpoint, return result. | httpx |
| `integrations/manifest.py` | Generate the **ConfigMap + Secret YAML** for the persist panel (def references secret by `secret_ref`, never inline). | PyYAML |
| `integrations/api.py` | FastAPI router for `/api/integrations/*` + serve `static/integrations.html`. | registry, openapi_tools, dispatch, manifest |
| `integrations/mcp_tools.py` | **Unchanged stub** — "coming next" tab. | — |

New dependency: **PyYAML** (added to `requirements.txt`). `httpx` is already present.

### Integration def schema (ConfigMap `integrations.yaml`)

```yaml
integrations:
  - name: Inventory API
    type: openapi
    base_url: http://inventory.svc.internal/v1   # overrides the spec's server
    enabled: true
    auth:
      type: api_key_header        # none | bearer | api_key_header
      header: X-API-Key           # only for api_key_header
      secret_ref: inventory-api-key   # key in the mounted Secret; omitted for none
    operations:                   # only these become tools
      - getItems
      - getItem
      - reserveItem
    spec_url: http://inventory.svc.internal/v1/openapi.json   # optional, for re-parse
```

A tool def emitted to the model:

```json
{"type":"function","function":{
  "name":"getItem","description":"Get one item",
  "parameters":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"]}}}
```

## 5. Backend API (new routes, served by `integrations/api.py`)

| Method + path | Body | Returns | Powers |
|---|---|---|---|
| `GET /api/integrations` | — | `[{id,name,type,base_url,enabled,tool_count,source:"config"\|"session",status}]` | list page |
| `POST /api/integrations/parse` | `{spec_url?\|spec_text?}` | `{title,server,operations:[{operationId,method,path,summary}]}` | **Fetch & parse** |
| `POST /api/integrations/test` | `{base_url,auth}` | `{ok,status,detail}` | **Test connection** (warns, never blocks) |
| `POST /api/integrations` | `{name,type,base_url,auth,operations[]}` | `{id, manifest:{configmap_yaml,secret_yaml}}` | **Save** (activate live + return YAML) |
| `PATCH /api/integrations/{id}` | `{enabled}` | `{ok}` | enable/disable toggle |
| `DELETE /api/integrations/{id}` | — | `{ok}` | remove a **session** integration |
| `GET /api/integrations/{id}/manifest` | — | `{configmap_yaml,secret_yaml}` | re-show persist panel |
| `GET /integrations` | — | `static/integrations.html` | the page |

The whole admin router is gated behind `ENABLE_INTEGRATIONS_ADMIN` (default `true`
in the starter; documented as something to disable/network-restrict in prod).

## 6. Data flow

**Register (UI):** `/parse` (fetch spec in-VPC, list ops) → operator picks ops +
auth → `/integrations` (activate live; secret held in **process memory**) → returns
YAML → operator applies it (`kubectl apply` or commit to Nuon app + `nuon sync`) →
on next pod start `config.py` loads from the mounted ConfigMap+Secret → registry
rebuilds `TOOLS`.

**Chat with tools:** user turn → model called with `TOOLS` → if the response has
`tool_calls`, `dispatch.py` calls each in-VPC endpoint with injected auth →
results appended as `tool` messages → model called again → final assistant reply.
**Loop capped at 5 iterations.** Reply may include a **tool-call trace** (good for
the demo and the audit story).

## 7. Secret handling (sovereign bit)

- Persisted secrets live only in the mounted **K8s Secret**; defs reference them
  by `secret_ref`.
- A **session-added** secret (typed in the UI, not yet persisted) is held in
  **process memory only**, emitted **once** into the Secret YAML, and **never
  returned by any GET**. Plaintext never reaches the browser on read and never
  lands in the ConfigMap.

## 8. Chat state (stateless backend + client-side persistence)

Current `/api/chat` is stateless (`{message}` → `[system, user]` only) — no
multi-turn memory, and the frontend keeps messages only in the DOM (reload wipes
them). Both are addressed **without server state**:

- `/api/chat` request shape changes from `{message}` to **`{messages: [...]}`**
  (the full visible conversation) so the model — and the tool-call loop — has
  multi-turn memory. The server prepends the system prompt; it stores nothing.
- `static/index.html` keeps the conversation array and **persists it to
  `localStorage`**, restoring on load, plus a **"Clear chat"** control.
- Per-request tool-loop intermediate messages are internal; only visible
  user/assistant turns are persisted client-side (fuller agent-step memory = future).

**Server-side chat history / audit is explicitly deferred to Tier 3** ("Sovereign:
full audit" in the README). Persisting chat over crown-jewel systems is a
compliance decision (retention/encryption/PII) the customer opts into, not a
default.

## 9. Error handling

- `/parse`: unreachable/unparseable spec → `400` + clear message, shown inline.
- `/test`: timeout/non-2xx → status shown; **save still allowed** (warn).
- **dispatch**: endpoint down / auth fail / timeout → return a structured
  **tool-error** back to the model (it explains gracefully) + record in the trace.
- No `tool_calls` → ordinary chat. Existing **503-on-cold-model** behavior preserved.

## 10. Security / access (called out honestly)

Tier 0 ships **no app auth**, so `/integrations` is as exposed as the chat. The
docs must state production deployments **front this with ingress/auth and
network-restrict the admin surface**; the admin API is gated by
`ENABLE_INTEGRATIONS_ADMIN`. Spec/base URLs are fetched server-side (SSRF
surface) — acceptable because operator-controlled and in-VPC, but **documented**,
with an optional "private hosts only" guard noted as an extension.

## 11. Deploy / Helm changes (`src/charts/chatbot/`)

- New templates: `configmap-integrations.yaml` (`chatbot-integrations`) and
  `secret-integrations.yaml` (`chatbot-integration-secrets`), both rendered from
  Helm values and **empty by default** (Tier 0 ships no integrations).
- `deployment.yaml`: mount the ConfigMap at `/etc/chatbot/integrations.yaml` and
  the Secret at `/etc/chatbot/secrets` (optional mounts), and add env
  `INTEGRATIONS_CONFIG`, `INTEGRATIONS_SECRETS_DIR`, `ENABLE_INTEGRATIONS_ADMIN`.
- `values.yaml` / `components/values/chatbot.yaml`: an `integrations: []` block
  (and an empty secret block). Operators either fill these via Nuon (GitOps) **or**
  apply the UI-generated YAML standalone — the chart mounts the named objects if
  present.
- `/health` already reports `tools` count; keep it.

## 12. Testing

- **Unit:** spec→tool-defs (fixture spec), dispatch request-building + auth
  injection (mocked httpx), manifest YAML generation, registry enable/disable +
  `TOOLS` derivation, `/api/chat` messages-shape handling.
- **Integration:** an in-process **fake OpenAPI service** (FastAPI) + FastAPI
  `TestClient`: register via `/parse`+`/integrations`, then a **stubbed model
  client** emits a `tool_call`; assert dispatch hits the fake service and the
  result feeds back into a final reply. Runs locally **without Ollama** (model
  client mocked).

## 13. File-by-file change summary

- `src/app/integrations/config.py` — **new**
- `src/app/integrations/registry.py` — **new**
- `src/app/integrations/openapi_tools.py` — flesh out stub (parse → tool defs)
- `src/app/integrations/dispatch.py` — **new**
- `src/app/integrations/manifest.py` — **new**
- `src/app/integrations/api.py` — **new** (router)
- `src/app/integrations/mcp_tools.py` — unchanged (stub)
- `src/app/main.py` — mount router; `/api/chat` → messages shape + tool-call loop
- `src/app/static/integrations.html` — **new** (registry + modal + persist panel)
- `src/app/static/index.html` — localStorage history + "Clear chat" + nav link
- `src/app/requirements.txt` — add PyYAML
- `src/charts/chatbot/templates/{configmap-integrations,secret-integrations}.yaml` — **new**
- `src/charts/chatbot/templates/deployment.yaml` — mounts + env
- `src/charts/chatbot/values.yaml`, `components/values/chatbot.yaml` — integrations block
- `src/app/integrations/README.md` — update (UI exists now; OpenAPI working, MCP next)
- tests — **new** under `src/app/` (unit + integration)

## 14. Future / not now

- MCP dispatch (wire the stub + a "MCP servers" tab).
- Basic + mTLS auth; SSRF private-hosts guard.
- Server-side chat history + full audit (Tier 3).
- Separate flagship: **Open WebUI on Nuon** / **Dify on Nuon** configs (own apps).
