# debug-bundle

> [!NOTE]
> First-response diagnostics for install `{{ .nuon.install.id }}` when something's
> wrong. Collects the bundle you'd otherwise gather by hand — pod state, events,
> recent logs, and a live endpoint probe — in one recorded run you can attach to
> a ticket.

## What it collects

1. **describe-and-events** — pod status, `describe` output, and the 50 most recent
   namespace events.
2. **recent-logs** — the last 200 log lines from both `chatbot` and `ollama`.
3. **endpoint-probe** — a single verbose `curl` reporting the HTTP status and
   latency. Non-failing by design, so the bundle completes even when the service
   is down.

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
> Read-only and safe to run during an incident. Follow with **reconcile-drift** or
> **break-glass** once you know what's wrong.
