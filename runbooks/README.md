# Runbooks

Named, multi-step operational procedures you run on demand against an install —
from the dashboard's **Runbooks** tab or `nuon runbooks --install-id <id>`. Each
runbook is a `<name>.toml` (the steps) plus a `<name>.md` (a rendered README that
templates in live install data).

Onboarding is automatic: creating an install deploys the app and warms the model, so
it comes up ready. These runbooks are for **operating** an install afterward.

Every runbook here operates on this app's real components (`chatbot`, `ollama`,
`certificate`, `application_load_balancer`) and actions (`deployment_status`,
`alb_healthcheck`, `break_glass_remediation`).

| Runbook | Scenario | Steps |
|---------|----------|-------|
| [`full-health-check`](./full-health-check.md) | **Health check** — many signals at once | nodes · `deployment_status` · model server · `alb_healthcheck` · endpoint |
| [`debug-bundle`](./debug-bundle.md) | **Debug** — something's gone wrong | describe + events → logs (chatbot + ollama) → endpoint probe (read-only) |
| [`reconcile-drift`](./reconcile-drift.md) | **Drift reconciliation** — re-apply desired state | `sandbox_reprovision` → `component_deploy` ollama + chatbot → verify |
| [`break-glass`](./break-glass.md) | **Break glass** — recorded emergency, elevated access | `break_glass_remediation` (assumes the break-glass role) → verify |

## Step types used

- `action` — run an existing action by `action_name`, or an inline `command` /
  `inline_contents` with `timeout`, `env_vars`, and optional `role`.
- `component_deploy` / `component_tear_down` — deploy or tear down a component,
  optionally with its dependents (`deploy_dependents`).
- `sandbox_reprovision` / `sandbox_deprovision` — re-apply or tear down the sandbox
  infrastructure (`skip_component_deploys` to leave components alone).

See the [Runbooks guide](https://docs.nuon.co/guides/runbooks) for the full schema.
