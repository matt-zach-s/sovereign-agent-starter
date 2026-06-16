# BYOC Agent Starter

A **self-hosted chatbot + a tiny open-weight LLM**, deployable into a customer's own
cloud account with [Nuon](https://nuon.co). It's a **starting line** for building
sovereign agentic tools: the model, the app, and (when you extend it) the
integrations all run inside the customer's boundary — no frontier API calls leave
the cluster.

The example app is deliberately a simple chatbot. The value is everything around it:
a self-hosted model, a one-line "swap your frontier API call" layer, and an
integration scaffold for wiring in your own internal systems.

## What gets deployed (Tier 0)

Into the customer's AWS account, on EKS, **CPU-only — no GPU**:

```
chatbot_image (docker_build)  ──► your chat app image
ollama        (helm)          ──► self-hosts the tiny model, OpenAI-compatible API
chatbot       (helm)          ──► the chat app, base_url-swapped to Ollama
certificate   (terraform)     ──► ACM cert (reused from nuonco/example-app-configs)
alb           (helm)          ──► public HTTPS endpoint (reused)
```

The model is a customer input (`model`, default `llama3.2:3b`). First request pulls
the model (~1–3 min on CPU), then it's resident.

## Complexity tiers

| Tier | Adds | Compute |
|------|------|---------|
| **0 — Hello world** (this kit) | chat UI + self-hosted tiny model | small CPU node, no GPU |
| **1 — Wire your systems** | register OpenAPI/MCP tools (`src/app/integrations/`) | still CPU |
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
`matt-zach-s/byoc-agent-starter` via a connected repo).

```bash
# app name MUST match the directory name
nuon apps create --name=byoc-agent-starter
nuon sync                       # syncs this app config
# then create an install against a customer AWS account from the dashboard/CLI
```

## The swap layer

`src/app/main.py` uses the **standard OpenAI client**, pointed at the self-hosted
endpoint:

```python
client = OpenAI(base_url=os.environ["OPENAI_BASE_URL"],  # ...ollama:11434/v1
                api_key="ollama")
```

To migrate an existing OpenAI-based app, you change `OPENAI_BASE_URL` and nothing
else. (An optional Anthropic-compatible gateway is a Tier-2 add-on.)

## The integration scaffold

`src/app/integrations/` is where you turn the chatbot into an agent over your own
systems — via **OpenAPI specs** or **MCP servers**, both reachable inside the VPC.
Empty in Tier 0 by design. See `src/app/integrations/README.md`.

## Cost & sovereignty notes

- Tier 0 is CPU-only; the cost floor is the EKS cluster + one small node, not a GPU
  fleet. Reaching "hello world" never requires a GPU quota request.
- No frontier API keys are stored (`secrets.toml` is empty) because the model is
  self-hosted. Prompts, data, and (once you add them) integration credentials stay
  inside the customer's account.
