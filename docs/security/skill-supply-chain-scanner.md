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

## Load-Time Integrity

The package hash covers every file in the package except the bytecode cache
files Python writes into a `__pycache__` directory (`<module>.<cache tag>.pyc`,
optionally with `.opt-N`). Any other file there, a `.py` source or a `.pyc`
with another name included, is hashed like the rest. A lock approved by an
earlier release, whose hash also covered the cache files, still matches while
every file, caches included, is the one that was approved.

Before the runtime loads a package's handler code (at startup, on install, on
`plugin_reload`), it hashes the files on disk again and compares the result
with the approved `package_hash` in the lock. When they differ, the package is
not loaded: its tools stay unregistered, the runtime logs
`skill_package_modified_not_loaded` and emits a `skill_package.modified` audit
event once per changed hash, `plugin_reload` answers that the package changed
after approval, and the registry item's `integrity.status` is `modified`
(otherwise `verified`), which the Skills tab shows on the package's card. An
operator reinstalls and reviews the package to load it again.

Handler code loads from the `.py` sources only. Python neither reads nor writes
a bytecode cache while the runtime registers a package's handlers, so a cache
file planted next to a handler, or next to a module the handler imports when it
loads, does not run in place of the verified source. That holds only during
registration: a module package code imports later, at tool-call time (which
needs package code that puts its own directory on `sys.path`), goes through
Python's normal `__pycache__` lookup, and those cache files are not covered by
the hash.

A rollback restores the previous lock, not the previous files. When the files
on disk no longer hash to that revision's `package_hash`, for example because
the update overwrote the same directory, the rollback is refused with
`skill.package_modified` and the current revision stays installed; reinstall
the wanted version instead (D-037).

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
