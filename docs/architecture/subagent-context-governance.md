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
- `target_agent_id?`: optional; when set it must name the parent's own agent,
  since a child run never acts as another agent (`subagent.policy_denied`).
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
task creation during a retry. The in-process map holds a child only while it
runs: it is dropped when the child finishes, times out or is cancelled.

## Limits And Policy

Default local/dev limits:

- maximum 2 concurrent child-runs per parent task
- maximum 4 total child-runs per parent task
- timeout default 180s, cap 600s
- nested child-runs disabled

Child-runs do not relax parent policy. The runtime applies normal ToolRegistry,
ExecutionPolicy, approval, sandbox, MCP risk, audit, and runtime event paths.

A child's capabilities are a subset of its parent's. At spawn the child gets
the parent's capability envelope: the parent's agent, its core tool allowlist
(less `task`) and its task kind. The child acts as the parent's agent, so its
workspace, inbox, squad access, approval grants and memory scope are the
parent's. A core tool outside the envelope is denied before the policy gate
(`child_run_capability_denied`), and a child run without an envelope gets no
tools. The dispatcher's `execute_tool` applies the same check to every tool
call of a child, so a `workflow_run` step inside a child is held to the
envelope too. The child is judged by the parent's task kind, so execution-policy rules
keyed on it bind the child too. Memory writes and sensitive recall are never
granted: the normalized context policy carries neither, whatever the request
asks for.
Every allowed child toolset runs the child read-only, and read-only denies
every write (`read_only_policy`) whatever execution-policy rule matches and
whatever approval grant the run holds, so a grant given to the parent never
lets its child write.
A child of a scheduled dry-run parent is a dry run too: the envelope carries
the parent's dry-run flag and scheduled job and run ids, the child gets the
dry-run prompt rules, a fresh provider turn and dry-run tools (writes are
blocked), and its result lists the `dry_run` warning. The child never
finalizes the parent's scheduled run.
A child starts from a copy of its parent turn's context, so it inherits the
parent's per-turn settings (such as `agent_mode`) and its total spend. When a
child finishes, its cost is added to the parent's total. The budget check
(`MAX_TOTAL_BUDGET_USD`) is the same pre-check the parent's own turn gets: it
runs when each child starts, against the parent's total at that moment, and
refuses a child once that total reaches the budget. It reserves nothing, so
the children that start before any of them finishes (up to the 2 concurrent
child-runs per parent) all pass the check against the same total and together
can take the parent's total past the budget. Only a child that starts after
the total reaches the budget is refused.
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
