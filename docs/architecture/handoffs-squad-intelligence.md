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
