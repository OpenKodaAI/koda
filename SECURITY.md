# Security Policy

## Reporting A Vulnerability

Do not disclose exploit details in a public issue.

Instead, contact the maintainers privately with:

- a clear summary of the issue
- affected version, tag, or commit
- reproduction steps
- expected impact
- any suggested mitigation or patch if available

## Supported Versions

Security fixes are expected to target the current maintained branch of the repository unless maintainers explicitly document additional support windows.

## Disclosure Expectations

- give maintainers time to triage and confirm the issue
- avoid publishing proof-of-concept details until a fix or mitigation is available
- coordinate timelines when public disclosure is necessary

## Sensitive Areas

The following areas should be treated as security-sensitive:

- runtime command execution and sandbox policy
- control-plane access and bootstrap tokens
- secrets storage and provider credentials
- file and path validation
- runtime and artifact object-storage access
- Postgres-backed control-plane and runtime state
- external integrations and approval-requiring operations
