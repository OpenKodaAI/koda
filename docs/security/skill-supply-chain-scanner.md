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

A `review_required` package installs only after an operator accepts the review
in the agent's Skills tab, which calls the operator-authenticated control-plane
route `POST /api/control-plane/agents/{agent_id}/skills/packages/install` with
`review_accepted=true`, a non-empty `review_note` and the `package_hash` the
review screen showed next to the scanner version and verdict. The install scans
the package again and refuses it with `skill.review_hash_mismatch` when the
files no longer match that hash. The lock records the review in
`operator_review`: the note, the time, the reviewer, the `package_hash`, the
`scanner_version` and the scan decision. The review does not weaken scanner
findings, ExecutionPolicy, or per-agent skill/package allowlists.

The model cannot accept a review. The `plugin_install` tool takes only `path`,
ignores any review fields in its call, and a `review_required` package fails
with `skill.policy_denied` until an operator approves it (D-031).

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
