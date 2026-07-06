# OWASP ASVS Remediation Matrix

Date: `2026-04-05`

This matrix is intentionally pragmatic. It maps Koda's current hardening work to OWASP ASVS control families and highlights what is implemented in-repo versus what still depends on deployment operations.

| ASVS Area | Koda Status | Current Controls |
| --- | --- | --- |
| V1 Architecture, Design and Threat Modeling | Partial | Repository-level threat model, explicit LLM/tool abuse scenarios, documented trust boundaries, security assessment and residual-risk tracking. |
| V2 Authentication | Improved | Control plane defaults to token auth, operator browser access requires a sealed session cookie, empty Telegram allowlists fail closed. |
| V3 Session Management | Improved | Stable `WEB_OPERATOR_SESSION_SECRET` required for real operator sessions, HTTP-only cookies, `SameSite=Strict`, secure cookies in production, no operator token in URL or browser storage. |
| V4 Access Control | Improved | Browser requests no longer inherit backend control-plane tokens, cross-site mutations blocked, integration grants default much closer to deny-by-default, runtime access tokens stay capability-scoped. |
| V5 Validation, Sanitization and Encoding | Improved | JSON payload validation, origin validation for dashboard mutations, MCP hostname resolution checks for SSRF, safer runtime payload sanitization for attach flows. |
| V6 Stored Cryptography | Improved | Web operator cookies are sealed with AEAD, attach tokens are hashed at rest, secret material remains encrypted in control-plane storage. |
| V7 Error Handling and Logging | Partial | Audit and runtime payloads redact sensitive attach material better than before; ongoing work still depends on deployment log routing and secret scrubbing outside the repository. |
| V8 Data Protection | Improved | Sensitive attach data removed from browser payloads, operator tokens avoided in query strings, stronger default handling of session and integration secrets. |
| V9 Communications | Improved | Production web security headers, stronger CSP/connect policy, DB TLS validation, SSH host-key validation, runtime attach relays replacing direct credential-bearing URLs. |
| V10 Malicious Code | Partial | Curated MCP catalog no longer relies on floating `@latest` for hardened entries; additional dependency governance and artifact signing still depend on CI/CD and release operations. |
| V11 Business Logic | Partial | Explicit operator session and per-bot grant model reduce privilege confusion, but destructive agent workflows still require continuous review of approval flows and prompts. |
| V12 Files and Resources | Partial | Safe-path and tool guardrails remain part of the runtime, but production filesystem isolation and host hardening remain deployment responsibilities. |
| V13 API and Web Service | Improved | Control-plane proxy no longer treats backend tokens as browser auth, runtime attach APIs return relays instead of raw websocket credentials, fail-closed auth posture is stronger by default. |
| V14 Configuration | Improved | Quickstart now provisions a stable web operator secret, control-plane auth defaults to token mode, public docs reflect secure bootstrap expectations. |

## Controls Still Outside Repository Scope

The following ASVS expectations cannot be fully satisfied by repository changes alone:

- production TLS certificate lifecycle and HSTS preload decisions
- reverse-proxy header trust and secure cookie forwarding
- network ACLs, WAF policy, and DDoS controls
- host IAM, secret vaulting, and backup protection
- centralized logging, retention, alerting, and incident response workflows
- independent penetration testing and formal assurance evidence

## Exit Criteria For A Stronger “Ready” State

Koda should only be described as strongly ASVS-ready in production when the repository controls above are combined with:

- a locked-down reverse proxy and TLS configuration
- documented secret rotation procedures
- monitored audit and runtime logs
- recurring dependency and SAST scans in CI
- periodic access review for operators, agents, integrations, and MCP connections
