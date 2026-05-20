# Sandbox Doctor Runbook

This runbook defines the Phase 2 KG-06 operational contract for effective
sandbox policy, deny-before-execute behavior, and doctor diagnostics.

## Effective Sandbox Policy

`sandbox_policy.v1` is computed for each agent/session/task before risky work
starts. It is a product contract, not just a readiness check.

Required fields:

- `policy_id`, `schema_version`, `agent_id`, `session_id?`, `task_id?`.
- `source`, `fingerprint`, `created_at`.
- `channel`: `channel_type`, `is_group`, `remote_session`,
  `identity_status`, and any explicit remote-policy grant.
- `filesystem`: read roots, write roots, denied roots, denied mount patterns.
- `environment`: allowed env keys, denied env patterns, redacted keys.
- `network`: egress mode, allowed domains/CIDRs, private-network rule.
- `shell`: allow/deny, command mode, timeout.
- `browser`: allow/deny, allowed domains, cookie/session posture.
- `mcp`: isolation strategy, allowed servers, denied servers, native fallback.
- `resources`: max duration, max processes, memory/cpu hints.
- `degraded_reasons`, `warnings`.

## Deny Before Execute

The sandbox gate runs before environment provisioning, shell/terminal/browser
start, workspace mutation, file/git write, and MCP execution.

Hard denies:

- secret-looking mounts or env exposure
- denied filesystem root or path pattern
- private network egress without an explicit grant
- custom MCP server with unresolved or unsafe isolation
- native isolation fallback for code execution, secret access, or destructive
  write
- unknown sandbox profile where the requested action is mutating, networked, or
  code-executing
- remote or group channel context whose identity is not explicitly allowed
- remote or group channel context attempting write, network, secret, destructive,
  code, unknown MCP, skill, or channel actions without an explicit remote policy

The denial response uses the shared error envelope with category
`policy_denied` and includes `run_graph_node_id` when available.

## Doctor Payload

Doctor responses are machine-readable:

- `doctor_version` / `schema_version`: `sandbox_doctor.v1`
- `status`: `passed`, `degraded`, `failed`, or `unavailable`
- `checks`: id, title, status, severity, scope, message, user_action, evidence
- `effective_policy`: includes `policy_version: sandbox_policy.v1`,
  isolation kind, risk class, network mode, mounts, env keys, decision, and
  allowed flag, plus safe channel context fields
- `degraded_components`
- `warnings`
- `generated_at`

Required checks:

- sandbox policy resolved
- runtime kernel authority and health
- cgroup hard/soft mode
- command guard / security core health
- MCP isolation strategy and native fallback risk
- stale capability snapshots
- unknown MCP risk count
- env secret exposure posture
- forbidden mounts
- egress/private-network policy
- remote/channel identity and unsafe remote default
- browser private-network/cookie posture
- approval/grant health

## CLI And Dashboard

`scripts/doctor.py --strict` must report sandbox and MCP risk checks in addition
to existing hardening checks. The dashboard should show a compact doctor card on
runtime/control-plane operational surfaces with status, top failing checks, and
actions. The UI should not infer policy from local heuristics; it consumes the
doctor payload.

Runtime-local endpoint:

- `GET /api/runtime/tasks/{task_id}/sandbox-doctor`

Control-plane endpoint:

- `GET /api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/sandbox-doctor`

The task detail payloads also include `sandbox_doctor` so execution detail and
runtime room views can render the card without product mocks.

## Validation

- Unit tests for policy normalization and fingerprint stability.
- Deny tests for forbidden mount, secret env, private egress, native isolation
  high-risk MCP, unknown sandbox profile, and code execution without hard
  isolation.
- Channel deny tests for untrusted remote/group identities and unsafe remote
  actions without `explicit_remote_policy`.
- Doctor tests for pass, warning, fail, and degraded runtime dependency states.
- Doctor tests must show remote/channel failures under `scope: "channel"`.
- RunGraph/audit tests for sandbox deny and degraded doctor outcomes.
- Docs must include rollback: disable the new gate only by restoring the prior
  policy config and leaving audit/runtime traces intact.
