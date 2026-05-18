# Top-Tier Phase Contracts

This document is the Phase 0 contract package for the Koda top-tier roadmap. It
turns the research backlog into delivery rules that every later phase must
follow before code, UI, tests, docs, and release work are considered complete.

Phase 0 covers:

- **KG-15:** delivery operations by agent team.
- **KG-14:** scale, resilience, performance, and user-facing error feedback.

The goal is not to change runtime behavior in Phase 0. The goal is to make the
next phases decision-complete, measurable, and safe to execute in a dirty
worktree.

## Roadmap Order

| Phase | Canonical epics | Primary outcome | Blocked-before rule |
|---|---|---|---|
| 0 | KG-15, KG-14 | Delivery program, SLOs, validation gates, handoff format | No KG-01 work starts without this contract and closeout. |
| 1 | KG-01, KG-02, KG-03, KG-04 | AgentTurn, ToolRegistry, native tools with XML fallback, HITL | No broad `queue_manager.py` rewrite before AgentTurn snapshots. |
| 2 | KG-05, KG-06, KG-07 | RunGraph/replay, sandbox/doctor, MCP risk taxonomy | No marketplace, channels, or broad plugins before fail-closed policy. |
| 3 | KG-09, KG-10 | Ephemeral `task`, squads preservation, context governance | No generic multi-agent product before child-run lifecycle is stable. |
| 4 | KG-08 | Skills, plugin SDK, scanner, provenance, rollback | No public marketplace before scanner and rollback pass. |
| 5 | KG-11 | Evals, metrics, trajectory export, release quality | No release-quality claims without deterministic replay/smoke gates. |
| 6 | KG-12, KG-13 | Channel gateway, onboarding, docs, OSS polish | No channel routing before identity, pairing, and unknown-sender deny. |

## Owners And Write Sets

| Track | Owner role | Write set | Produced interfaces |
|---|---|---|---|
| Integration | Lead / Integrator | Phase docs, architecture contracts, issue map, shared schemas | Phase contract, merge order, closeout gate. |
| Backend Runtime | Runtime owner | Queue/runtime/store/provider-adjacent code and tests | Runtime states, queue/recovery events, metrics, timeouts. |
| Tools / Policy / Security | Security owner | Tool policy, approvals, MCP, sandbox, scanner, security tests | Risk classes, deny paths, approval defaults, redaction rules. |
| Frontend Product | Product UI owner | Runtime, executions, DLQ, overview, control-plane UI and tests | UI state model, error rendering, contract-backed mocks. |
| QA / Evals | QA owner | Tests, fixtures, E2E, load, fault, replay smoke, CI gates | Validation matrix and pass/fail artifacts. |
| Docs / DX | Docs owner | ADRs, operator/dev docs, examples, troubleshooting | Docs gate, migration notes, rollback notes. |
| Release / Ops | Release owner | Readiness, health, smoke, release checklist, operations docs | Release train, rollback, residual-risk record. |

Rules:

- Files already dirty in the local worktree are user-owned unless the active
  task explicitly claims them.
- Shared files such as `koda/services/queue_manager.py`, migrations, runtime
  event contracts, shared TypeScript types, and docs indexes have a single
  integration owner per phase.
- Frontend may start from versioned test fixtures, but no product flow can close
  on unversioned mocks.
- Security relaxations cannot be used to make tests pass. The phase fails until
  deny/fail-closed behavior is correct.

## Required Phase Contract

Phase 1 contract artifacts:

- [AgentTurn Contract](agent-turn-contract.md)
- [ToolRegistry And Native Tools](tool-registry-native-tools.md)
- [HITL Approval Runbook](../operations/hitl-approval-runbook.md)

Phase 2 contract artifacts:

- [RunGraph And Replay Contract](run-graph-replay.md)
- [Sandbox Doctor Runbook](../operations/sandbox-doctor-runbook.md)
- [MCP Risk Taxonomy](../security/mcp-risk-taxonomy.md)

Phase 3 contract artifacts:

- [Subagent Task And Context Governance](subagent-context-governance.md)
- [Subagent Task Runbook](../operations/subagent-task-runbook.md)

Phase 4 contract artifacts:

- [KodaSkill And Plugin SDK](koda-skill-plugin-sdk.md)
- [Skills And Plugin Package Runbook](../operations/skills-plugin-runbook.md)
- [Skill Supply-Chain Scanner](../security/skill-supply-chain-scanner.md)

Phase 5 contract artifacts:

- [Evals, Trajectory Export, And Release Quality](evals-release-quality.md)
- [Evals And Release Quality Runbook](../operations/evals-release-runbook.md)

Phase 6 contract artifacts:

- [Channel Gateway And Onboarding Readiness](channel-gateway-onboarding.md)
- [Channel Gateway Runbook](../operations/channel-gateway-runbook.md)
- [Onboarding Readiness Runbook](../operations/onboarding-readiness-runbook.md)

Every phase must publish the following before feature slices are marked ready:

| Contract area | Required contents |
|---|---|
| API | Endpoint path, method, request schema, response schema, status codes, auth/capability expectation. |
| Events | Event type, payload schema, severity, correlation fields, retention expectation. |
| DB / migrations | Migration plan, rollback plan, compatibility window, data retention and redaction behavior. |
| Types / schemas | Python dataclass or typed dict shape, TypeScript shape, JSON Schema where the value crosses a boundary. |
| Frontend fixtures | Versioned fixtures derived from the API/event schema; fixture-only mocks must stay in tests. |
| Error taxonomy | Error envelope, category, retryability, user action, trace/detail reference. |
| RunGraph | Required nodes, parent/child relation, redaction, replay behavior, audit/metric links. |
| Operations | SLO profile, load/fault target, cleanup expectations, degraded-mode UX. |
| Docs | ADR, operator guide, developer guide, troubleshooting, migration/rollback, examples when applicable. |

## Error Envelope

User-facing operational errors must use this minimum envelope once a boundary is
formalized:

```json
{
  "code": "runtime.dependency_timeout",
  "category": "timeout",
  "message": "Runtime dependency timed out.",
  "retryable": true,
  "user_action": "Retry the task or inspect dependency health.",
  "trace_id": "optional-trace-id",
  "run_graph_node_id": "optional-node-id",
  "detail_ref": "optional-doc-or-event-ref"
}
```

Categories:

| Category | Meaning | Default user action |
|---|---|---|
| `configuration` | Missing or invalid setup. | Open settings or run doctor. |
| `permission` | Missing operator, workspace, channel, or integration permission. | Request access or edit grants. |
| `policy_denied` | ExecutionPolicy, sandbox, MCP, or approval rule blocked the action. | Inspect policy and choose a safer action. |
| `dependency_unavailable` | Provider, MCP, browser, Postgres, sidecar, or network dependency is unavailable. | Wait, retry, or inspect health. |
| `timeout` | Work exceeded a declared timeout. | Retry, cancel, or reduce scope. |
| `validation` | Request, tool args, schema, or fixture contract failed validation. | Correct input or schema. |
| `retryable` | The system can retry safely. | Retry or wait for automatic retry. |
| `non_retryable` | Retrying may duplicate effects or cannot succeed unchanged. | Change input or resolve the root cause. |
| `internal` | Unexpected product bug. | Inspect trace and logs; open an issue. |

## Runtime State Model

The UI and API must use these operational states for agent work where
applicable:

| State | Meaning | Required UX |
|---|---|---|
| `queued` | Accepted but not yet running. | Show queue position or backpressure reason when available. |
| `running` | Lease or runtime owner is actively processing. | Show live activity and last event time. |
| `retrying` | Previous attempt failed and retry policy is active. | Show attempt count and retry cause. |
| `stalled` | Heartbeat, lease, stream, or event progress is stale. | Show inspect, cancel, and recovery guidance. |
| `degraded` | Partial dependency or runtime capability is unavailable. | Show degraded component and next action. |
| `failed` | Terminal failure. | Show error envelope, trace, DLQ/retry eligibility. |
| `cancelled` | Operator or system cancellation reached terminal state. | Show cancellation source and cleanup status. |
| `completed` | Work finished successfully. | Show result, trace, artifacts, cost, and validation notes. |

## RunGraph And Observability Requirements

KG-05 will implement the full RunGraph product, but every earlier phase must
declare enough trace/audit/metric coverage to be migrated into RunGraph later.

Required node or event concepts:

- `queue_wait`
- `lease_acquire`
- `lease_renew`
- `lease_lost`
- `lease_reaped`
- `model_call`
- `tool_call`
- `policy_gate`
- `approval_request`
- `approval_decision`
- `dependency_call`
- `breaker_open`
- `retry_scheduled`
- `dlq_inserted`
- `cancellation`
- `resource_cleanup`
- `user_facing_error`
- `child_run`
- `artifact`
- `cost`
- `eval_case`
- `eval_run`
- `trajectory_export`
- `release_quality`
- `channel_message_received`
- `channel_identity_decision`
- `channel_pairing`
- `onboarding_readiness`
- `first_task`
- `first_trace`

Each concept must have correlation fields for agent, task/run, attempt,
session, runtime environment when available, and user-visible detail reference
when the event affects the UI.

## Per-Phase Definition Of Done

A phase is not complete until all applicable items are true:

- Backend is implemented and covered by focused unit/integration tests.
- User-facing behavior is integrated with real API/events.
- No production UI depends on unversioned mocks.
- Security deny/fail-closed paths pass.
- Load/concurrency and fault gates run for queue, runtime, subagents, channels,
  providers, MCP, browser, Postgres, or long-running work touched by the phase.
- Resource cleanup is covered for success, failure, cancel, and restart where
  the phase owns resources.
- RunGraph/audit/metrics requirements are declared and covered.
- Docs include ADR, operator guide, developer guide, troubleshooting,
  migration/rollback, and examples where applicable.
- Obsidian daily/session handoff records validation, residual risks, and next
  phase kickoff.

## Phase 6 Closeout Gate

KG-12 and KG-13 close only when:

- `channel_gateway.v1` denies unknown Telegram senders before enqueue, records
  pending senders, supports pairing code, approve, block, and revoke, and keeps
  empty `ALLOWED_USER_IDS` fail-closed.
- Legacy `ALLOWED_USER_IDS` remains compatible for configured users, while
  blocked or revoked gateway identities override legacy allowance.
- Gateway identities, unknown senders, pairing codes, gateway events, and
  readiness runs persist through migration `040_channel_gateway_onboarding_v1`
  with fallback JSON locks for rollback-safe local use.
- Dashboard channel UI consumes backend gateway payloads and does not duplicate
  policy/risk decisions.
- `onboarding_readiness.v1` reports provider, runtime, storage, sandbox, MCP,
  memory, channel, first task, first trace, docs, and release quality checks.
- First-task onboarding uses the normal dashboard/runtime path and does not
  bypass queue, policy, audit, metrics, or RunGraph-compatible events.
- Docs index, OpenAPI contract, operator runbooks, frontend contracts, backend
  tests, web tests, and Obsidian handoff are updated before KG-12/KG-13 are
  marked implemented.

## Handoff Format

Every role closes its slice with:

```markdown
## Handoff
- Epic / KT IDs:
- Owner:
- Files changed:
- Contracts produced:
- Contracts consumed:
- Validation run:
- Validation not run:
- Residual risks:
- Rollback:
- Next blocker:
```
