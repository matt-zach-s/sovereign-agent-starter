# Integration scaffold (Tier 1)

Tier 0 is a pure chatbot. This directory turns it into an **agent that acts on your
own internal systems** — without any data or credentials leaving the customer's cloud
boundary.

## The `/integrations` admin UI

An operator-facing page lives at `/integrations`. It is off by default and gated by
the `ENABLE_INTEGRATIONS_ADMIN` env var (set to `"true"` to enable it). Because Tier 0
ships with **no app-level authentication**, you must front `/integrations` with
ingress auth and network-restrict it in production before exposing it.

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

### MCP (coming next)

MCP server support is stubbed out and not yet functional. It will follow the same
UI flow once implemented.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `INTEGRATIONS_CONFIG` | JSON blob describing registered integrations (loaded from the ConfigMap) |
| `INTEGRATIONS_SECRETS_DIR` | Directory where K8s Secret volume mounts land (one file per secret key) |
| `ENABLE_INTEGRATIONS_ADMIN` | Set to `"true"` to enable the `/integrations` admin page |

## Dispatch heuristic

When the model calls a tool, the app dispatches to the real in-VPC endpoint using a
simple heuristic:

- Path placeholders (`{id}`, etc.) are substituted from the tool-call arguments.
- `GET` and `DELETE` requests send remaining arguments as query parameters.
- `POST`, `PUT`, and `PATCH` requests send remaining arguments as a JSON body.

This covers the common case. Complex parameter layouts (mixed query + body, form
data, file uploads) will need a custom dispatch layer.

## Security notes

- **Tier 0 has no app-level authentication.** Front `/integrations` with ingress auth
  (e.g. an OAuth2-proxy sidecar or ALB authentication rules) and restrict its network
  exposure in production.
- Spec URLs and base URLs are fetched **server-side**; the browser never makes
  out-of-cluster requests on behalf of the operator.
- Secrets are stored in a K8s Secret and mounted as files. They are **never returned
  to the browser** after the initial save and never appear in API responses.

## Why this matters

The reasoning (self-hosted model) and the action layer (these tools, pointed at
internal systems) both run inside the customer's account. That is what makes a
regulated enterprise able to deploy an agent over its crown-jewel systems without
a third-party subprocessor — the gap this starter kit exists to fill.
