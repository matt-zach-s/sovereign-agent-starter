# onboard-install

> [!NOTE]
> The onboarding checklist for install `{{ .nuon.install.id }}`, encoded as one
> repeatable run. Warm the self-hosted model, make sure the app is deployed, and
> verify it's serving — the same procedure for every new customer.

## What it does

1. **warm-model** — waits for the Ollama deployment, then pulls the configured
   model `{{ .nuon.inputs.inputs.model }}` so the first user request isn't cold.
2. **deploy-app** — `component_deploy` of `chatbot` with `deploy_dependents`, which
   also brings up the load balancer in front of it.
3. **smoke-test** — curls the public endpoint until it returns healthy.

## Target

{{ if and .nuon.sandbox.populated .nuon.sandbox.outputs }}
<nuon-group gap="8" align="center">
  <nuon-badge theme="info" variant="code">GET</nuon-badge>
  <nuon-badge theme="default" variant="code">https://{{ .nuon.inputs.inputs.sub_domain }}.{{ .nuon.sandbox.outputs.nuon_dns.public_domain.name }}/health</nuon-badge>
</nuon-group>
{{ else }}
The target URL is available once the sandbox is deployed.
{{ end }}

> [!TIP]
> Safe to re-run — it converges the install to "model warmed, app deployed,
> endpoint healthy."
