# reconcile-drift

> [!NOTE]
> When install `{{ .nuon.install.id }}` has drifted from its desired state, this
> runbook re-applies that desired state from the bottom up — infrastructure first,
> then the components — and verifies the result.

## What it does

1. **detect-drift** — prints the live cluster state so you can see what changed
   before reconciling.
2. **reconcile-infra** — `sandbox_reprovision` with `skip_component_deploys`, which
   re-applies the sandbox Terraform (networking, DNS, cluster) without touching the
   app components.
3. **reconcile-model** — `component_deploy` of `ollama` to restore the model server.
4. **reconcile-app** — `component_deploy` of `chatbot` with `deploy_dependents`, so
   the app and its load balancer are re-applied together.
5. **verify** — curls the public endpoint until it returns healthy.

## Target

{{ if and .nuon.sandbox.populated .nuon.sandbox.outputs }}
<nuon-group gap="8" align="center">
  <nuon-badge theme="info" variant="code">GET</nuon-badge>
  <nuon-badge theme="default" variant="code">https://{{ .nuon.inputs.inputs.sub_domain }}.{{ .nuon.sandbox.outputs.nuon_dns.public_domain.name }}/health</nuon-badge>
</nuon-group>
{{ else }}
The target URL is available once the sandbox is deployed.
{{ end }}

> [!WARNING]
> `reconcile-infra` re-applies sandbox infrastructure. Run **debug-bundle** first to
> confirm the drift, then reconcile.
