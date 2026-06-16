# Integration scaffold (Tier 1)

Tier 0 is a pure chatbot. This directory is where you turn it into an **agent that
acts on your own internal systems** — without any data or credentials leaving the
customer's cloud boundary.

Two extension points, both abstract on purpose:

| File | Use it to… | Set env var |
|------|------------|-------------|
| `openapi_tools.py` | Expose any internal HTTP service that publishes an **OpenAPI/Swagger** spec as model tools | `OPENAPI_SPEC_URLS` (comma-separated, in-VPC) |
| `mcp_tools.py` | Expose any **MCP server** running inside the environment as model tools | `MCP_SERVER_URLS` (comma-separated, in-VPC) |

## How it fits together

1. `load_openapi_tools()` / `load_mcp_tools()` return OpenAI-compatible tool
   definitions. They are empty in Tier 0.
2. `main.py` collects them into `TOOLS` and passes them to the self-hosted model
   on every chat call (`tools=TOOLS`) once non-empty.
3. You implement the **dispatch** side: when the model emits a tool call, call the
   real in-VPC endpoint and feed the result back.

## Why this is the point

The reasoning (self-hosted model) and the action layer (these tools, pointed at
internal systems) both run inside the customer's account. That is what makes a
regulated enterprise able to deploy an agent over its crown-jewel systems without
a third-party subprocessor — the gap this starter kit exists to fill.
