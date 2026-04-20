# Operational Baseline

Date: `2026-04-05`

This checklist is the minimum operational baseline for running Koda with a security posture consistent with the hardening implemented in this repository.

## Pre-Deployment

- Keep the control plane bound to localhost or private interfaces unless a reverse proxy is intentionally fronting it.
- Terminate TLS at the reverse proxy and forward secure headers consistently.
- Set and rotate `CONTROL_PLANE_API_TOKEN`, `RUNTIME_LOCAL_UI_TOKEN`, and `WEB_OPERATOR_SESSION_SECRET`.
- Keep `.env`, master-key files, and persistent volumes readable only by the service account or root.
- Do not expose Postgres, object storage, memory, or security service ports publicly unless there is a deliberate network policy around them.
- Review every curated or custom MCP connection before enabling it for an agent.

## Agent And Integration Governance

- Grant write-capable tools only when an agent truly needs them.
- Treat shell, git, file mutation, browser-write, webhooks, workflows, plugins, and MCP-write as privileged capabilities.
- Require explicit integration grants per agent and review them during publication and release changes.
- Re-validate grants after major prompt or workflow changes, not only after integration setup.
- Keep private-network browser access disabled unless a runtime flow explicitly depends on internal services.

## Session And Secret Handling

- Never place operator or runtime credentials in URLs, screenshots, or shared runbooks.
- Rotate bootstrap tokens after administrative turnover or suspected exposure.
- Revoke stale MCP OAuth tokens and unused integration credentials.
- Audit logs and traces for secret leakage whenever a new integration or attach surface is introduced.

## Continuous Verification

- Run dependency audits for Python, Node, and Rust on pull requests and on a schedule.
- Run SAST, secret scanning, and container scanning in CI with blocking thresholds for high and critical findings.
- Rebuild the quickstart and rerun the doctor checks after security-sensitive dependency updates.
- Keep a regression suite for operator auth, attach relays, SSRF blocking, and least-privilege grants.

## Release Checklist

- Confirm the web tier is not receiving unnecessary privileged backend tokens.
- Confirm `CONTROL_PLANE_AUTH_MODE` is not left open in production.
- Confirm the reverse proxy sends HTTPS and secure cookie semantics end to end.
- Confirm runtime attach flows expose only relays, never raw tokens or credential-bearing websocket URLs.
- Confirm MCP/custom endpoint validation still blocks private or resolved-internal addresses.
- Confirm audit retention, backup policy, and observability are active in the target environment.

## Incident Response Triggers

Escalate immediately when any of the following occurs:

- unexpected operator-session invalidation or suspicious repeated web-auth failures
- runtime attach sessions appearing without matching operator intent
- MCP or integration traffic toward internal network ranges
- unexplained creation of destructive grants or policy broadening
- secrets appearing in audit payloads, screenshots, traces, or logs

## Formal Assurance Boundary

This baseline supports secure operation and repeatable maintenance.

It is not a substitute for:

- production pen testing
- cloud/IAM review
- compliance control evidence
- legal or contractual certification processes
