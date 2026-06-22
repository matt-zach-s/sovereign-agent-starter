# break-glass

> [!WARNING]
> Emergency, elevated-access remediation for install `{{ .nuon.install.id }}`. Use
> only during an incident — and use it *instead of* ad-hoc console access, so the
> elevated action is recorded and repeatable.

## What it does

1. **emergency-remediation** — runs the **break_glass_remediation** action, which
   assumes the install's break-glass IAM role
   (`{{ .nuon.install.id }}-sovereign-agent-starter-sandbox-break-glass`) and force-rolls
   the `chatbot` and `ollama` deployments.
2. **verify** — curls the public endpoint until it returns healthy, confirming the
   emergency action restored service.

## Why run break-glass *as a runbook*

The elevated role is scoped and defined in `break_glass.toml`; invoking it through a
runbook means every emergency intervention is logged in the install's run history
with who/what/when — the auditable alternative to someone logging into the console
under a shared admin role at 3 a.m.

## Target

{{ if and .nuon.sandbox.populated .nuon.sandbox.outputs }}
<nuon-group gap="8" align="center">
  <nuon-badge theme="info" variant="code">GET</nuon-badge>
  <nuon-badge theme="default" variant="code">https://{{ .nuon.inputs.inputs.sub_domain }}.{{ .nuon.sandbox.outputs.nuon_dns.public_domain.name }}/health</nuon-badge>
</nuon-group>
{{ else }}
The target URL is available once the sandbox is deployed.
{{ end }}
