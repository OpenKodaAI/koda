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

P3 requires `review_required` installs to include both `review_accepted=true`
and a non-empty `review_note`. The note is recorded with install audit metadata
and trust summary; it does not weaken scanner findings, ExecutionPolicy, or
per-agent skill/package allowlists.

Imported or legacy locks with `decision=review_required` but no preserved
`operator_review.accepted` evidence stay `blocked` and cannot become
`recommended`.

## Audit And Observability

Every scan/install/uninstall/rollback emits audit events. Runtime use of
package tools continues through ToolRegistry, ExecutionPolicy, approvals,
RunGraph, and metrics. The frontend renders backend findings and must not
reclassify risk locally.

Package tool execution is gated twice: prompt/native schema exposure requires
`skill_policy.enabled_skill_packages` and `tool_policy.allowed_tool_ids`, and
direct dynamic handler calls are denied by the dispatcher unless the same
runtime policy allows the package and tool.

Recommendation is evidence-backed. A package with no skill eval evidence is
`unreviewed`; failed required evals produce `eval_failed`; only passing required
offline `skill_eval.v1` checks can produce `recommended`.
