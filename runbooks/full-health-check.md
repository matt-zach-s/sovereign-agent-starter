# full-health-check

Checks the health of install `{{ .nuon.install.id }}` across every layer that has
to be working for the agent to serve traffic.

## What it checks

1. **node-health** — node readiness and capacity (`kubectl get nodes`, `top nodes`).
2. **workload-health** — runs the existing **deployment_status** action to report
   the `agent` namespace deployments.
3. **model-server-health** — Ollama rollout status and the list of pulled models,
   so you know the self-hosted LLM is actually loaded.
4. **ingress-health** — runs the existing **alb_healthcheck** action against the
   load balancer.
5. **endpoint-health** — curls the public endpoint and only passes on a healthy
   HTTP status.

## Target

{{ if and .nuon.sandbox.populated .nuon.sandbox.outputs }}
<nuon-group gap="8" align="center">
  <nuon-badge theme="info" variant="code">GET</nuon-badge>
  <nuon-badge theme="default" variant="code">https://{{ .nuon.inputs.inputs.sub_domain }}.{{ .nuon.sandbox.outputs.nuon_dns.public_domain.name }}/health</nuon-badge>
</nuon-group>
{{ else }}
The target URL is available once the sandbox is deployed.
{{ end }}

## Current component status

{{ if .nuon.components }}
| Component | Status |
|-----------|--------|
{{- range $name, $component := .nuon.components }}
| `{{ $name }}` | `{{ $component.status }}` |
{{- end }}
{{ else }}
No components are active in this install yet.
{{ end }}

> [!TIP]
> Safe to run any time — every step is read-only.
