# Sovereign Agent Starter

A **self-hosted chatbot + a tiny open-weight LLM**, deployed into a customer's own
cloud account with [Nuon](https://nuon.co) — the **day-0 starting line** for an
*operating* agent that does real work inside a customer's boundary: the model, the
app, and (when you extend it) the integrations all run in-account, with **no frontier
API calls leaving the cluster**.

The example app is deliberately a simple chatbot. The value is everything around it:
a self-hosted model, a one-line "swap your frontier API call" layer, and an
**integration scaffold (OpenAPI + MCP)** for wiring the agent into your own internal
systems.

### Who this is for, and why it's shaped this way

Built for teams — boutique AI-consulting firms and regulated-enterprise builders —
shipping bespoke agents into clients that are **sovereignty-forced** (data and
credentials can't leave the boundary) yet **can't staff a platform team** to run a
self-hosted stack. For them the hard part isn't building the agent; it's getting it
**through the security review and keeping it running across many clients**.

- **Sovereignty is a sign-off accelerant, not the product.** Self-hosting the model
  answers the three things that most often block an AI deployment — model provenance,
  data residency, and audit trail — *by construction*, which is what shortens the
  security review.
- **Don't run this kit standalone.** On its own it just relocates a Kubernetes +
  model-babysitting job into the client's VPC. Paired with **Nuon's in-account runner
  and the operational runbooks**, the lifecycle (provision → deploy → drift-reconcile →
  push-updates) is operated *for* the client — and reproducibly across **N different
  client clouds**, which is the actual prize.
- **vs. putting the agent in a client VPC over a managed model API** (e.g. Bedrock
  AgentCore): this keeps the **reasoning in-boundary**, not just the compute — the only
  shape that also survives true air-gap.

## What gets deployed (Tier 0)

Into the customer's AWS account, on EKS, **CPU-only — no GPU**:

```
chatbot_image (docker_build)  ──► your chat app image
ollama        (helm)          ──► self-hosts the tiny model, OpenAI-compatible API
chatbot       (helm)          ──► the chat app, base_url-swapped to Ollama
certificate   (terraform)     ──► ACM cert (reused from nuonco/example-app-configs)
alb           (helm)          ──► public HTTPS endpoint (reused)
```

The model is a customer input (`model`, default `qwen2.5:1.5b`). First request pulls
the model (~1–3 min on CPU), then it's resident.

## Complexity tiers

| Tier | Adds | Compute |
|------|------|---------|
| **0 — Hello world** (this kit) | chat UI + self-hosted tiny model | small CPU node, no GPU |
| **1 — Wire your systems** | add integrations via the `/integrations` UI (OpenAPI + MCP working) | still CPU |
| **2 — Production model** | swap Ollama for vLLM + a larger open model | GPU node group |
| **3 — Sovereign** | air-gap, RAG over your corpus, full audit | GPU + in-boundary stores |

## Try it locally first

```bash
docker compose up --build
# open http://localhost:8080   (first reply waits on the model pull)
MODEL=qwen2.5:1.5b docker compose up --build   # smaller/faster
```

## Deploy it with Nuon

Prerequisites: a Nuon account, the `nuon` CLI, and this repo **connected to Nuon**
(the `ollama`, `chatbot`, and `chatbot_image` components build from
`matt-zach-s/sovereign-agent-starter` via a connected repo).

```bash
# app name MUST match the directory name
nuon apps create --name=sovereign-agent-starter
nuon sync                       # syncs this app config
# then create an install against a customer AWS account from the dashboard/CLI
```

## Operational runbooks

`runbooks/` holds five **Runbook** archetypes — named, multi-step procedures you run
on demand against an install, with a rendered README per runbook (see
[`runbooks/README.md`](./runbooks/README.md)). They operate on this app's real
components (`chatbot`, `ollama`, `application_load_balancer`) and actions
(`deployment_status`, `alb_healthcheck`, `break_glass_remediation`).

| Runbook | Scenario | Step types it shows |
|---------|----------|---------------------|
| `onboard-install` | **Setup** — onboard a new install | inline action → `component_deploy` → curl |
| `full-health-check` | **Health check** — many signals at once | inline + `action_name` references |
| `debug-bundle` | **Debug** — collect diagnostics | inline (read-only, non-failing) |
| `reconcile-drift` | **Drift reconciliation** — re-apply desired state | `sandbox_reprovision` → `component_deploy` → curl |
| `break-glass` | **Break glass** — recorded emergency, elevated access | `action_name` (carries `break_glass_role`) |

Run from the dashboard's **Runbooks** tab or `nuon runbooks --install-id <id>`.

## The swap layer

`src/app/main.py` uses the **standard OpenAI client**, pointed at the self-hosted
endpoint:

```python
client = OpenAI(base_url=os.environ["OPENAI_BASE_URL"],  # ...ollama:11434/v1
                api_key="ollama")
```

To migrate an existing OpenAI-based app, you change `OPENAI_BASE_URL` and nothing
else. For multi-model routing, an Anthropic-compatible surface, virtual keys, or
request-audit logging, a self-hosted **LiteLLM** gateway is a Tier-2 add-on —
intentionally *not* in the Tier-0 first run, where there's a single model and nothing
to route yet.

## The integration scaffold

`src/app/integrations/` is where you turn the chatbot into an agent over your own
internal systems — without data or credentials leaving the customer's cloud boundary.
Empty in Tier 0 by design.

**Tier 1** adds a `/integrations` admin UI where an operator registers either an
**OpenAPI** service (paste its spec URL) or an **MCP server** (paste its in-VPC URL).
The app parses the spec / performs the MCP handshake server-side, lets you pick which
operations or tools to expose, stores any secret in a K8s Secret (secrets never reach
the browser), and activates the integration live — its tools become callable by the
agent on the next turn. It then emits ready-to-apply ConfigMap/Secret YAML to persist
the config; the app never writes to the cluster itself. The admin API supports
**app-level auth** (`INTEGRATIONS_ADMIN_TOKEN`) — an unauthenticated tool-registration
endpoint holds credentials to your internal systems, so set a token before exposing it.

See `src/app/integrations/README.md` for env vars, the dispatch heuristic, and
security notes.

## Cost & sovereignty notes

- Tier 0 is CPU-only; the cost floor is the EKS cluster + a small 2-node group, not
  a GPU fleet. Reaching "hello world" never requires a GPU quota request. (Two nodes
  is the floor because the Nuon sandbox runs Kyverno in HA — that's the platform
  baseline, not the app; a single node can't schedule it alongside the model server.)
- No frontier API keys are stored (`secrets.toml` is empty) because the model is
  self-hosted. Prompts, data, and (once you add them) integration credentials stay
  inside the customer's account.

## Provisioning notes (sandbox sizing gotchas)

Learned the hard way — get node sizing right **before the first provision**:

- **≥2 nodes is the floor.** The sandbox installs Kyverno in HA (9 pods); a single
  node can't fit that + the model server, so `desired_size=1` makes the Kyverno
  Helm release fail during sandbox provisioning. `sandbox.tfvars` ships `min=2 /
  desired=2 / max=4`.
- **You can't grow an existing EKS managed node group's `desired_size` via a
  re-sync/reprovision.** The upstream module sets `ignore_changes=[desired_size]`,
  and AWS also rejects raising `min` above the current `desired`
  (`Minimum capacity 2 can't be greater than desired size 1`). A reprovision reuses
  the *same* node group, so sizing changes don't take. To change node count: either
  **tear down and create a fresh install** (new node group, born at the new size),
  or scale the node group directly in AWS (`aws eks update-nodegroup-config`).
