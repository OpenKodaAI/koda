# Security Readiness

This section captures Koda's application-security baseline as of `2026-04-05`.

It is intentionally focused on `hardening + certification readiness`, not on claiming a formal external certification.

Use this set when you need:

- a professional security assessment of the current product surface
- a threat model centered on agents, tools, MCP, runtime attach, and operator flows
- an OWASP ASVS-oriented remediation view
- an operational checklist for secure deployment and continuous maintenance

## Documents

- [Security assessment](assessment.md)
- [Threat model](threat-model.md)
- [OWASP ASVS remediation matrix](asvs-remediation-matrix.md)
- [Operational baseline](operations-baseline.md)

## Scope Notes

- These documents cover the repository, the bundled local stack, and the public web/control-plane/runtime surfaces.
- They do not replace a formal external penetration test, production architecture review, or legal/compliance audit.
- Residual risks that depend on reverse proxies, TLS termination, IAM, backups, WAF, logging, and production hosting remain explicitly called out in the documents below.
- Repository automation includes GitHub-native scanning plus an optional dedicated Snyk workflow when `SNYK_TOKEN` is
  configured. The repository-level [`.snyk`](../../.snyk) file excludes generated build artifacts, local virtualenvs,
  and packaged release bundles from Snyk Code import so scans stay focused on first-party manifests and shipped source.
