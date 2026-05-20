# Subagent Task And Context Governance

Phase 3 implements KG-09 and KG-10 with two additive contracts:

- `child_run.v1` for ephemeral Delegate Task child runs.
- `context_governance.v1` for metadata-only context block accounting and fencing.

The feature is intentionally separate from persistent Squad Room behavior.
`task` launches bounded child-runs for one parent execution; `agent_delegate`
and Squad tools continue to represent durable multi-agent coordination.

## child_run.v1

The ToolRegistry exposes `task` with UI title `Delegate Task`.

Minimum request fields:

- `goal`: short child objective.
- `prompt`: full child brief.
- `tasks[]`: optional fan-out list; singular calls remain supported.
- `target_agent_id?`: optional control-plane agent prompt/profile.
- `toolset`: defaults to `read_only`; Phase 3 allows `read_only`, `analysis`,
  and `research`.
- `timeout_seconds`: default 180, capped at 600.
- `max_context_tokens`, `max_cost_usd?`, `context_policy`, `return_schema?`.

Result fields:

- `child_run_id`
- `child_task_id`
- `status`
- `summary`
- `structured_output`
- `artifacts`
- `cost_usd`
- `run_graph_node_id`
- `warnings`
- `error?`

Child runs are persisted as normal tasks with:

- `source_task_id = parent_task_id`
- `source_action = "child_run"`

The additive Postgres table `child_runs` stores metadata, request payload,
context policy, context summary, status, result, error, deadlines, and
timestamps. If the table is unavailable, readers can reconstruct a partial tree
from task lineage and RunGraph data.

Idempotency is keyed by parent task, parent attempt, tool-call signature, and
child index. The database enforces `(agent_id, parent_task_id,
idempotency_key)` and the in-process tool handler also prevents duplicate child
task creation during a retry.

## Limits And Policy

Default local/dev limits:

- maximum 2 concurrent child-runs per parent task
- maximum 4 total child-runs per parent task
- timeout default 180s, cap 600s
- nested child-runs disabled

Child-runs do not relax parent policy. The runtime applies normal ToolRegistry,
ExecutionPolicy, approval, sandbox, MCP risk, audit, and runtime event paths.
Phase 3 fails closed for write, network-write, destructive, unknown, or
unrecognized child toolsets until a stricter approval path is implemented.

Backpressure and policy errors use operational envelopes:

- `subagent.fanout_limit_exceeded`
- `subagent.queue_saturated`
- `subagent.timeout`
- `subagent.policy_denied`
- `subagent.runtime_unavailable`

## context_governance.v1

Context governance is assembled from `PromptBudgetResult` metadata. It never
serializes the compiled prompt or raw context text.

Each block includes:

- `block_id`
- `category`
- `source`
- `token_estimate`
- `status`: `included`, `dropped`, or `review_required`
- `include_reason`
- `drop_reason`
- `redaction`
- `risk`
- `provenance`

The default policy is minimal and metadata-only:

- allow `base`, `runtime_rules`, and `tool_contracts`
- deny `secrets` and `pending_approval`
- do not include memory, artifacts, or Squad context unless explicitly allowed
- mark sensitive context for review or fence it before child delivery

The child-run prompt receives only the parent brief plus the approved block
metadata. Secrets, raw pending approvals, sensitive mounts, and suspicious
memory are dropped or marked review-required.

## RunGraph

Phase 3 extends the Phase 2 graph by populating:

- `child_run` nodes under the `task` tool result.
- `context_block` nodes from `context_governance.v1`.
- `child_run` edges from the parent tool result to each child.
- runtime events for `context_governance.evaluated`.

Replay remains offline. Child-run payloads contain summaries, task ids, costs,
warnings, and error envelopes, not raw prompts or secret context.

## API And UI

Runtime task detail and operational execution detail expose:

- `child_runs[]`
- `context_governance`
- parent/child RunGraph nodes

The dashboard shows:

- child-run tree/list with open execution links
- cancel and interrupt actions for active child-runs
- context block included/dropped/review-required summary
- RunGraph and replay with real backend payloads

Frontend policy remains display-only. It consumes backend-provided actions and
payloads without duplicating risk heuristics.

## Rollback

Rollback is additive:

- disable or remove `task` from enabled tool policy
- ignore/export/drop `child_runs`
- keep historical task lineage via `source_task_id/source_action`
- keep RunGraph fallback reconstruction from existing traces

No existing Squad Room, XML fallback, native tool calls, HITL approval, sandbox
doctor, or MCP risk behavior needs to change for rollback.
