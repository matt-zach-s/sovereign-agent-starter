# migrate-and-roll-out

> [!NOTE]
> The encoded "ship a breaking change" procedure for install `{{ .nuon.install.id }}`:
> run the migration, roll out the new version, and only succeed once the service
> is healthy again — instead of three separate manual steps you have to remember
> to do in order.

## What it does

1. **apply-migration** — runs the schema/data migration as a one-off Kubernetes
   Job and blocks until it completes. (The demo uses a `busybox` Job to stand in
   for a real migration; swap in your own image/command.)
2. **roll-out** — `component_deploy` of `chatbot` with `deploy_dependents`, so the
   new version and everything downstream of it (the load balancer) roll together.
3. **health-check** — curls the public endpoint, retrying until it returns healthy,
   so the run fails if the rollout didn't come back.

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
> To change the served model rather than the schema, update the `model` input and
> re-run this runbook — the roll-out + health-check stay identical.
