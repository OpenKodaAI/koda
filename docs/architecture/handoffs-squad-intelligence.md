# Handoffs, Route Quality, And Synthesis Readiness

This document defines the P4/P5 coordination additions around the existing
Squad Room contracts. Handoffs extend `squad_delivery.v1`; they do not replace
room messages, reply obligations, tasks, or private child runs.

## Handoff Event

`handoff_event.v1` is stored as a transcript-visible `squad_messages`
`system_event` metadata payload. Required fields:

- `handoff_id`
- `thread_id`
- `source_agent_id`
- `destination_agent_ids`
- `handoff_kind`: `transfer`, `consult`, `parallel_consult`, or `return`
- `reason`
- `context_policy`
- `deadline`
- `return_criteria`
- `status`: `requested`, `accepted`, `declined`, `timed_out`, `returned`, or `failed`
- `run_graph_node_id`
- `correlation_id`

Parallel handoff is represented either as one event with multiple
`destination_agent_ids` or as correlated events sharing `correlation_id`.
Coordinator synthesis must see an explicit return, timeout, decline, or failure
before treating handoff work as terminal.

The coordinator engine records a handoff's destinations as the agents it gives
a task. A task-less handoff gives each selected participant a task first. The
post-turn task-cycle check (`_maybe_enqueue_squad_coordinator_synthesis`) then
derives the outcome of a `requested` or `accepted` handoff once every
destination has answered, through a visible task result for the cycle or a
reply obligation it answered on the cycle's source message. The queue worker
runs this check, like the other squad follow-ups, after it releases the
per-user lock it holds for post-processing, because queueing the synthesis
turn takes that lock again (D-019). It runs them once the turn's answer is
recorded in the thread, even if a later post-processing step fails. The
outcome is:

- `returned` when every answer succeeded;
- `failed` when a destination's task result has `payload.status` `failed` or
  `cancelled`. Every way the queue ends a destination's turn without an
  answer records one, and then runs the same check:
  - a run that fails (a provider error, exhausted retries, a runtime
    guardrail or an unexpected exception) and a turn that fails before its
    run starts (a budget overrun, or an error while its query context is
    prepared, such as a failed squad access check) get a failed task result
    with the error and a failed task;
  - a cancelled run (`/cancel` or scheduler control) gets a cancelled task
    result with the cancellation reason and a cancelled task;
  - a pending task that depends on a task that failed, was cancelled or was
    escalated can never run, so it is cancelled with a task result from its
    assignee that names that task.

  An answered reply obligation does not turn a failed result into
  `returned`. The failure is added to the synthesis disclosures, so the
  synthesis prompt names the agents that failed.

The check queues the coordinator synthesis before it records the outcome. A
dispatch that fails (for example a rejected tasks insert) is tried twice more,
after 1 s and 2 s. When every attempt fails, as while the runtime shuts down,
the outcome is not recorded: the handoff stays open and the room shows the
`[agent_dispatch_unavailable]` events, rather than a `returned` handoff with no
answer. Nothing runs the check for that cycle again later yet.

Once the synthesis is queued, an event with that status and the same
`handoff_id` is recorded once, and it supersedes the open event. Its
idempotency key is the handoff id and status, and the handoff writer asks the
thread store to deduplicate on it (`post_thread_message(..., dedupe=True)`);
other posts store their idempotency key without deduplicating. A status-change
event has a delivery status that matches it (`completed`, `failed`,
`timed_out`, or `blocked`) and is not addressed to the destinations again. On
the web, the dashboard delivery watcher leaves handoff cycles to this post-turn
check, so it does not add a second synthesis.

The check is not atomic yet (D-058, M2-E4-T3), and nothing stops a second
dispatch of the synthesis, only a second outcome event. It reads the cycle's
open tasks up to four times, 0.5 s apart, so a destination that finishes while
another is still open keeps checking for about 1.5 s. In one runtime the queue
worker awaits the check before it starts the next turn, so one user's turns do
not race. Under the supervisor, where each destination runs in its own runtime,
two destinations that finish within about 1.5 s of each other can each queue a
synthesis, and the room then gets two final answers. Nothing times a handoff
out yet. The reply-cycle path has no handoffs.

## Route Quality

`SquadDeliveryRouteDecision` includes:

- `candidate_scores`
- `excluded_candidates`
- `route_explanation`
- `required_tools`
- `required_skills`
- `quality_inputs`

Routing excludes agents fail-closed when a required tool or skill is missing.
Low-confidence routing returns a clarification fallback instead of sending work
to an unsuitable agent. Current signals are bounded and deterministic: success
score, timeout rate, load, cost, eval score, tool access, and skill access.

## Synthesis Readiness

`synthesis_readiness.v1` validates coordinator synthesis against completed
evidence. The gate checks:

- open room tasks
- open reply obligations
- open child runs
- open handoffs
- failed, declined, cancelled, or timed-out terminal work

Final synthesis is allowed only when open work is resolved or when the final
answer explicitly declares the affected timeout, decline, failure, or block.
Allowed evidence sources are task results, transcript-visible replies,
artifacts, completed child runs, and terminal handoff events.

## Observability

RunGraph recognizes `handoff_event` as a node type and the completeness verifier
supports a `handoff` scenario. Metrics are emitted for handoff lifecycle, route
quality, and synthesis-gate allow/block decisions.

## Residual Risks

This P4/P5 slice is not Robust. Remaining work includes authenticated Squad
Room timeline E2E, restart/idempotency with open handoffs, live load/fault
tests, continuous outcome-history ingestion for routing, and a dedicated route
explanation panel.
