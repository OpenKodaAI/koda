# Improvement Proposal Contract

`improvement_proposal.v1` is the canonical self-improvement queue for Koda. It
turns eval failures, runs, user corrections, timeouts, tool failures, and manual
operator input into reviewable change proposals. Memory quality signals and
knowledge candidates feed the queue as `evidence_refs`, not as a parallel
self-improvement queue. It does not apply persistent runtime changes
automatically.

## Contract

Required fields:

- `schema_version`: `improvement_proposal.v1`
- `proposal_id`, `agent_id`
- `source_kind`: `run`, `eval`, `user_correction`, `timeout`, `dead_letter`,
  `tool_failure`, or `manual`
- `source_ref`: stable source reference such as suite id plus case key and
  failure category
- `proposal_type`: `memory`, `skill`, `prompt`, `routing_profile`,
  `tool_policy`, `eval_case`, or `docs`
- `summary`, `evidence_refs`, redacted `diff_preview`
- `risk_class`: `low`, `medium`, `high`, or `critical`
- `validation_plan`, service-recorded `validation_result`, `rollback_plan`
- `status`, `reviewer`, `idempotency_hash`, `run_graph_node_ids`
- timestamps and `status_history`

Allowed statuses are `draft`, `pending_review`, `approved`, `rejected`,
`validating`, `applied`, `rolled_back`, and `failed`.

## Lifecycle

New proposals may be created only as `draft` or `pending_review`. A draft may
be incomplete. A `pending_review` proposal, or a draft being approved, must
have source evidence, redacted diff preview, risk class, validation plan, and a
structured rollback plan.

The operator flow is:

1. Review `pending_review`.
2. Approve or reject.
3. Validate approved proposals with offline eval or smoke evidence.
4. Apply only after post-approval validation passes, RunGraph lifecycle
   evidence exists, and rollback effects can be recorded.
5. Roll back applied proposals through the effect ledger when needed.

Invalid transitions fail closed. Rejected proposals do not mutate runtime state.
Failed validation records the validation result and prevents apply. Validation
results supplied at creation are rejected; validation must be recorded by the
lifecycle.

## Control-Plane API

Canonical endpoints:

- `GET /api/control-plane/agents/{agent_id}/improvement-proposals`
- `POST /api/control-plane/agents/{agent_id}/improvement-proposals`
- `GET /api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}`
- `POST /api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/approve`
- `POST /api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/reject`
- `POST /api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/validate`
- `POST /api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/apply`
- `POST /api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/rollback`

List responses use `{ "schema_version": "improvement_proposal.v1", "items": [...] }`.
Single/action endpoints return the proposal object directly. Error responses
use an operational envelope under `error` with `code`, `category`, `message`,
`retryable`, and `user_action`.

Eval suites create `pending_review` proposals for failed cases by default.
Those proposals carry eval run/case, source task, RunGraph, and RunGraph node
evidence. They remain inactive until explicit approval, validation, and apply.

## Persistence, Audit, And Metrics

Persistence is additive through `improvement_proposals` and
`improvement_proposal_effects`. The proposal table stores redacted previews,
JSON evidence, validation and rollback plans, status history, lifecycle
RunGraph node ids, and a server-computed idempotency hash to dedupe repeated
failures.

Lifecycle operations emit `improvement_proposal.*` audit events and
`koda_improvement_proposal_events_total` metrics. Proposal payloads must not
store secrets, raw prompts, raw compiled context, credentials, or unredacted
tool output.

## Rollback

Apply requires a structured rollback plan with ledger effects. P1 only ships a
safe `ledger_only` effect executor, which records reversible evidence without
editing runtime prompt, skill, memory, routing, policy, eval, or docs state.
Proposal-specific runtime executors must be added and tested before those
proposal types can mutate their targets. Rollback marks `rolled_back` only
after all applied effects are restored in reverse order.
