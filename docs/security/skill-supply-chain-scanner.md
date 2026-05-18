# Skill Supply-Chain Scanner

The Phase 4 scanner is a static gate for local skill/plugin packages. It does
not import, execute, or evaluate package code.

## Contract

Scanner output uses `skill_scan.v1`:

- `decision`: `allow`, `review_required`, or `deny`
- `severity`: highest finding severity
- `findings`: id, severity, category, message, path, user action
- `permissions_requested`
- `risk_classes`
- `redactions`
- `package_hash`
- `file_hashes`
- `scanner_version`

## Deny Rules

The scanner denies:

- path traversal or symlink escape
- files over the package size budget
- missing handlers for declared tools
- invalid JSON Schema or manifest shape
- secret-looking files or literal credentials
- install scripts or lifecycle hooks
- dangerous imports or calls such as `subprocess`, `eval`, `exec`, and
  `os.system`
- unknown permissions
- `secret_access`, `code_execution`, `destructive_write`, or `unknown` risk
  without an explicit review path
- tool id conflicts with core or already installed package tools

## Review Required

Network writes, private network access, low-confidence metadata, or broad write
permissions return `review_required`. Review does not bypass ExecutionPolicy or
approval. It only allows package install to proceed when local operator policy
accepts the risk.

## Audit And Observability

Every scan/install/uninstall/rollback emits audit events. Runtime use of
package tools continues through ToolRegistry, ExecutionPolicy, approvals,
RunGraph, and metrics. The frontend renders backend findings and must not
reclassify risk locally.
