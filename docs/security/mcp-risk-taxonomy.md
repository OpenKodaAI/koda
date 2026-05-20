# MCP Risk Taxonomy

This document defines the Phase 2 KG-07 risk taxonomy used by MCP discovery,
ToolRegistry metadata, ExecutionPolicy, approvals, doctor checks, and dashboard
grants.

## Risk Classes

| Risk class | Meaning | Default |
|---|---|---|
| `read_context` | Reads bounded context without external side effects. | Allow or preview according to agent policy. |
| `low_risk_write` | Bounded local or idempotent write with no external send/delete. | Preview or approval depending on policy. |
| `network_write` | Sends, creates, comments, publishes, posts, emails, webhooks, or mutates remote APIs. | Approval required. |
| `destructive_write` | Deletes, removes, archives, purges, overwrites, bulk mutates, or force changes state. | Approval required; retries guarded. |
| `secret_access` | Reads tokens, credentials, cookies, OAuth state, env secrets, keys, or secret-bearing resources. | Deny or explicit approval with scoped grant. |
| `code_execution` | Runs shell, scripts, eval, package install, browser JS, subprocesses, or remote code. | Deny unless sandbox policy permits and approval/grant exists. |
| `unknown` | Missing, conflicting, or low-confidence classification. | Fail closed; no silent allow. |

## Classification Inputs

The mapper may use MCP annotations, tool/resource/prompt name, description,
input schema keys, server transport, auth metadata, and runtime constraints.
Annotations are advisory, not authoritative.

Rules:

- `readOnlyHint=true` can only produce `read_context` when the schema and text
  have no mutation, network-write, secret, destructive, or code-execution
  indicators.
- `destructiveHint=true` produces `destructive_write`.
- `idempotentHint=true` lowers write retry risk only after the write class is
  known; it does not make a tool read-only.
- `openWorldHint=true`, remote API verbs, send/post/comment/webhook/email terms,
  or external URL mutation produce `network_write`.
- token/env/oauth/cookie/key/credential terms produce `secret_access`.
- shell/process/script/eval/install/execute/browser-js terms produce
  `code_execution`.
- Conflicting hints or missing schema produce `unknown`.

## Grants And Policy

Risk is stored with discovered MCP capability metadata and mirrored into
ToolRegistry definitions. The frontend renders backend risk and approval
defaults; it does not reclassify tools.

Discovered MCP tool payloads use canonical `mcp_risk.v1` classes:
`read_context`, `low_risk_write`, `network_write`, `destructive_write`,
`secret_access`, `code_execution`, and `unknown`. Approval defaults use the
execution decision vocabulary: `allow`, `allow_with_preview`, or
`require_approval`.

Legacy `always_allow`, `always_ask`, `blocked`, and `auto` policies remain
compatible, but they cannot silently downgrade `secret_access`,
`code_execution`, `destructive_write`, or `unknown` into allow. An explicit
operator grant must include server, capability id, risk class, scope, actor,
timestamp, and policy fingerprint.

## Fail-Closed Requirements

- Unknown tool/risk/schema/policy means deny or approval-required before
  execution.
- Approval does not classify unknown risk; classification must be resolved or
  the action stays blocked.
- Native MCP isolation fallback is degraded. High-risk classes require hard
  sandbox support or are denied.
- Every deny emits audit and RunGraph `policy_gate` / `user_facing_error`
  correlation when task context exists.

## Validation

- Unit tests for every risk class.
- Conflict tests for read-only plus destructive/secret/code indicators.
- Unknown-risk fail-closed tests.
- MCP snapshot persistence tests prove risk metadata is included.
- ExecutionPolicy tests prove high-risk classes require approval/grant.
- Frontend tests render risk badges and policy warnings from backend payloads.
