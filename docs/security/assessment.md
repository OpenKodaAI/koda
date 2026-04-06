# Security Assessment

Date: `2026-04-05`

Status: `ASVS readiness hardening in progress`

This assessment covers the Koda repository, the bundled web dashboard, the Python control plane and runtime, the MCP/integration execution layer, and the default Docker quickstart stack.

## Executive Summary

Koda's main risk concentration is not a single classic web flaw. The highest-risk paths sit at the intersection of:

- privileged operator access to the control plane
- LLM-driven tool execution
- MCP and third-party integrations
- runtime attach channels for browser and terminal access
- infrastructure secrets and durable state

The current hardening round moved the platform materially closer to a fail-closed posture by default. The most important improvements are:

- browser-originated control-plane access now requires a real operator session instead of inheriting server-side privilege
- local and production defaults were tightened so missing allowlists or auth tokens no longer imply open access
- runtime attach tokens are no longer returned to the browser as raw websocket URLs with embedded credentials
- attach tokens are hashed at rest and redacted from public runtime payloads
- MCP HTTP endpoints now reject hosts that resolve to private, loopback, link-local, multicast, or otherwise unsafe address ranges
- database TLS validation and SSH host-key validation now fail closed unless the operator explicitly opts into weaker development posture
- the curated MCP catalog no longer depends on floating `@latest` installs for the hardened entries touched in this round

## Highest-Priority Findings And Current Status

### Critical

1. Web proxy privilege inheritance
Status: remediated in this round.

The dashboard previously had a path where browser-originated control-plane requests could benefit from a privileged server token present in the web environment. This effectively collapsed the browser/operator trust boundary. The proxy now requires a sealed operator session cookie and forwards only that operator credential.

2. Runtime attach credential disclosure
Status: remediated in this round.

Attach responses previously exposed raw websocket endpoints and bearer-like attach tokens back to the browser surface. The browser-facing API now strips `attach.token`, `ws_url`, and `novnc_url`, replacing them with short-lived relay descriptors owned by the web server.

### High

3. Open authentication/authorization defaults
Status: materially reduced in this round.

`CONTROL_PLANE_AUTH_MODE` now defaults to `token`, and empty `ALLOWED_USER_IDS` now deny access instead of allowing everyone. The quickstart also provisions a stable web operator session secret so operator cookies do not depend on ephemeral in-memory secrets.

4. Cross-site dashboard mutations
Status: remediated in this round.

The dashboard now blocks cross-site mutations by validating `Origin` or `Referer` against the request origin in the Next.js proxy and route-level handlers.

5. SSRF through MCP HTTP transport
Status: remediated in this round.

Validation now resolves hostnames before allowing MCP HTTP/SSE connections and rejects destinations that land on private or unsafe network ranges.

6. Weak transport validation for DB and SSH
Status: remediated in this round.

Database TLS now verifies peer and hostname in the hardened path, and SSH tunnels no longer disable host-key verification by default.

### Medium

7. Floating MCP supply-chain defaults
Status: reduced in this round.

The curated MCP catalog entries updated here no longer default to `@latest`, and the Vercel entry no longer points at a nonexistent local package. This reduces surprise upgrades and lowers the risk of silently consuming breaking or malicious upstream changes.

8. Misleading auth warning for empty allowlists
Status: remediated in this round.

The runtime warning now correctly states that an empty allowlist denies all users instead of implying open access.

9. Browser security headers
Status: improved in this round.

The web app already shipped with a security-header baseline. Production CSP `connect-src` is now narrower, HSTS is emitted only in production, and `X-Permitted-Cross-Domain-Policies` is explicitly disabled.

## LLM- and Agent-Specific Threats

The core Koda threat model must treat the LLM runtime as a high-risk execution orchestrator rather than a passive assistant. First-class abuse paths include:

- prompt injection that attempts to widen tool permissions or bypass human approval
- tool abuse through shell, git, file, browser-write, workflow, webhook, or MCP-write capabilities
- sensitive data exfiltration through integrations or browser/runtime attach flows
- malicious MCP servers that misreport tool safety or weaponize side effects
- abuse of internal-only network reachability through browser automation or HTTP/SSE transports
- privilege confusion between operator-authenticated UI calls and backend service credentials

## Residual Risk

This hardening round does not make a defensible claim of “total security.” The largest remaining dependencies are operational:

- correct TLS termination and secure cookie forwarding at the reverse proxy
- secret rotation, revocation, and backup protection in the deployed environment
- IAM and access control around the host, Docker runtime, and supporting infrastructure
- WAF, rate limiting, and network exposure controls outside the repository
- centralized logging, alerting, and anomaly detection for abuse, credential theft, and failed auth
- independent penetration testing against the deployed environment and high-risk integrations

## Certification Readiness Statement

Koda can reasonably be described as `ASVS-readiness hardened` after this round only in the sense that the repository now has a stronger secure-by-default posture, an explicit remediation map, and operational guidance.

It must not be described as formally certified, formally homologated, or guaranteed secure without:

- an environment-specific production review
- evidence of control operation in deployment
- independent security testing
- formal sign-off by the relevant assurance process
