# Integration scaffold (Tier 1)

Tier 0 is a pure chatbot. This directory turns it into an **agent that acts on your
own internal systems** — without any data or credentials leaving the customer's cloud
boundary.

## The `/integrations` admin UI

An operator-facing page lives at `/integrations`, gated by the
`ENABLE_INTEGRATIONS_ADMIN` env var (defaults to `"true"`). **App-level auth is
available:** set `INTEGRATIONS_ADMIN_TOKEN` and every `/api/integrations*` call must
carry it (`X-Admin-Token: <token>` or `Authorization: Bearer <token>`) — the page
shell still loads and the UI prompts for the token. If no token is set the admin API
is open and the app logs a loud startup warning; in that case you must front
`/integrations` with ingress auth and network-restrict it before exposing it.

### OpenAPI flow (working end-to-end)

1. **Paste a spec URL.** The app fetches the OpenAPI/Swagger spec server-side (the
   URL never leaves the cluster) and parses it into a list of operations.
2. **Select operations.** Pick which endpoints the model is allowed to call.
3. **Enter a server-side secret.** The secret is stored in a Kubernetes Secret
   (`INTEGRATIONS_SECRETS_DIR` points to the mount path). It is never returned to the
   browser after it is saved.
4. **Activate live.** The integration goes active and the selected operations become
   model tools on the next chat turn.
5. **Persist via ConfigMap/Secret YAML.** The UI emits ready-to-apply Kubernetes
   manifests (ConfigMap for integration config, Secret for credentials). Copy these
   into your own GitOps repo or apply them directly. **The app never writes to the
   cluster** — it only emits YAML for you to apply.

### MCP flow (working)

1. **Choose "MCP server → tools"** in the Add-integration dialog and paste an in-VPC
   MCP server URL (Streamable HTTP / JSON-RPC).
2. **Connect & discover.** The app performs the MCP handshake server-side
   (`initialize` → `notifications/initialized` → `tools/list`) and lists the
   server's tools.
3. **Select tools, set auth, activate.** Selected tools become model tools on the
   next chat turn; calls are dispatched to the server via `tools/call`.
4. **Persist** the same way (ConfigMap/Secret YAML). MCP integrations can also be
   supplied at boot via the `MCP_SERVER_URLS` env var or the `integrations.yaml`
   ConfigMap (`type: mcp`).

The client speaks the core of the protocol over HTTP and is dependency-free (reuses
`httpx`); stdio transport and long-lived server→client streaming are documented
fork-it extensions (see `mcp_tools.py`).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `INTEGRATIONS_CONFIG` | JSON blob describing registered integrations (loaded from the ConfigMap) |
| `INTEGRATIONS_SECRETS_DIR` | Directory where K8s Secret volume mounts land (one file per secret key) |
| `ENABLE_INTEGRATIONS_ADMIN` | Set to `"true"` to enable the `/integrations` admin page |
| `INTEGRATIONS_ADMIN_TOKEN` | If set, require this token on every `/api/integrations*` call |
| `MCP_SERVER_URLS` | Comma-separated in-VPC MCP server URLs to expose as tools at boot |

## Dispatch heuristic

When the model calls a tool, the app dispatches to the real in-VPC endpoint using a
simple heuristic:

- Path placeholders (`{id}`, etc.) are substituted from the tool-call arguments.
- `GET` and `DELETE` requests send remaining arguments as query parameters.
- `POST`, `PUT`, and `PATCH` requests send remaining arguments as a JSON body.

This covers the common case. Complex parameter layouts (mixed query + body, form
data, file uploads) will need a custom dispatch layer.

## Security notes

- **App-level auth is available — turn it on.** Set `INTEGRATIONS_ADMIN_TOKEN`
  (Helm value `adminToken`) so the admin API rejects unauthenticated calls. Defense in
  depth: still front `/integrations` with ingress auth (an OAuth2-proxy sidecar or ALB
  auth rules) and restrict its network exposure. An unauthenticated tool-registration
  endpoint holds credentials to your internal systems — never expose it open.
- Spec URLs and base URLs are fetched **server-side**; the browser never makes
  out-of-cluster requests on behalf of the operator.
- Secrets are stored in a K8s Secret and mounted as files. They are **never returned
  to the browser** after the initial save and never appear in API responses.

## Why this matters

The reasoning (self-hosted model) and the action layer (these tools, pointed at
internal systems) both run inside the customer's account. That is what makes a
regulated enterprise able to deploy an agent over its crown-jewel systems without
a third-party subprocessor — the gap this starter kit exists to fill.
