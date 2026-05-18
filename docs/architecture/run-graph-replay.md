# RunGraph And Replay Contract

This document defines the Phase 2 `run_graph.v1` contract for KG-05. It turns
the existing flat execution trace, runtime events, approval records, and
execution episodes into a causal graph that can be inspected and replayed
offline without calling a provider.

## Contract

`run_graph.v1` is additive. Existing audit events, runtime events, task rows,
approval payloads, and execution episodes remain valid sources.

### RunGraphNode

Required fields:

- `node_id`: stable string id generated at the queue/runtime boundary.
- `graph_id`: stable graph id, normally `run:{agent_id}:{task_id}:attempt:{attempt}`.
- `agent_id`, `task_id`, `attempt`, `session_id?`, `env_id?`.
- `parent_node_id?`, `ordinal`, `node_type`, `status`.
- `started_at?`, `completed_at?`, `duration_ms?`.
- `summary`, `payload`, `redactions`, `refs`.
- `trace_id?`, `audit_event_id?`, `runtime_event_seq?`, `source`.

Allowed `node_type` values:

- `queue_wait`
- `lease_acquire`
- `lease_renew`
- `lease_lost`
- `lease_reaped`
- `model_call`
- `context_block`
- `tool_request`
- `tool_result`
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
- `runtime_event`

Allowed `status` values are `queued`, `running`, `retrying`, `stalled`,
`degraded`, `failed`, `cancelled`, `completed`, `blocked`, and `info`.

### RunGraphEdge

Required fields:

- `edge_id`: deterministic id derived from graph id, source, target, type, and ordinal.
- `graph_id`
- `from_node_id`
- `to_node_id`
- `edge_type`
- `ordinal`
- `payload`

Allowed `edge_type` values are `contains`, `caused_by`, `emits`, `uses`,
`approves`, `produces`, `retries`, `fails_to`, and `child_run`.

### Replay Bundle

`RunReplayBundle` reconstructs the trajectory from stored data only. It must not
call LLM providers, tools, MCP servers, browser sessions, or shell commands.

Required fields:

- `schema_version`: `run_replay.v1`
- `graph_id`, `agent_id`, `task_id`, `attempt`
- `replay_mode`: always `offline` for Phase 2
- `inputs`: redacted prompt/query/context summaries and hashes
- `model_outputs`: redacted output summaries, stop reason, usage and hash refs
- `tool_results`: tool id, redacted args/result preview, success, duration
- `approval_decisions`: decision, approved args or response summary, rationale
- `artifacts`: artifact refs and redacted labels, not raw file contents
- `costs`: provider/model/cost/usage summary
- `divergences`: missing or inconsistent source records

## Persistence

Phase 2 adds Postgres tables only:

- `run_graph_nodes`
- `run_graph_edges`
- optional `run_replay_snapshots`

Migrations must use `CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT
EXISTS`. Rollback is to ignore the tables or export/drop them after preserving
legacy audit/runtime traces. User task execution must continue if graph writes
fail.

## API

Control-plane endpoints:

- `GET /api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/run-graph`
- `GET /api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/replay`
- `GET /api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/sandbox-doctor`

Runtime-local endpoints:

- `GET /api/runtime/tasks/{task_id}/run-graph`
- `GET /api/runtime/tasks/{task_id}/replay`
- `GET /api/runtime/tasks/{task_id}/sandbox-doctor`

Responses must include an error envelope on failure and must redact sensitive
payloads by default. Sensitive expansion requires the existing scoped runtime
access path.

## Frontend

Execution detail shows a compact graph summary and replay action. Runtime task
detail includes `run_graph`, `run_replay`, and `sandbox_doctor` payloads, while
dedicated endpoints allow narrower refreshes. The runtime task room owns the
full graph viewer: tree/timeline modes, node filters, node detail drawer,
artifact links, approval links, and degraded/unavailable states. Production UI
must consume backend graph/replay contracts; mocks remain test-only fixtures.

Phase 3 adds KG-09/KG-10 graph sources:

- `child_run` nodes are emitted from `task` tool results and link parent runs to
  child task ids through `child_run` edges.
- `context_block` nodes are emitted from `context_governance.v1` summaries.
- The graph payload remains redacted; child-run nodes carry summaries, status,
  cost, warnings, and error envelopes instead of raw child prompts or fenced
  context.

## Validation

- Contract tests for serialization and deterministic ids.
- Redaction tests for prompt, tool args, provider output, env, path, token, and
  secret-shaped fields.
- Integration tests that generate nodes for model calls, tool requests/results,
  policy gates, approvals, retries, DLQ, runtime events, artifacts, and costs.
- Replay tests that prove no provider/tool/runtime call occurs.
- Frontend tests for graph viewer, filters, node detail, replay drawer, and
  unavailable/degraded states.
