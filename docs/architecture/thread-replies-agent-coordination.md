# Thread Replies And Agent Coordination

`thread_reply.v1` makes Squad Room replies operational. A reply can create a
tracked obligation for one or more active room agents, and the coordinator owns
the final synthesis once required replies are complete.

## Contract

Thread messages remain stored in `squad_messages`. The reply contract extends
that envelope with:

- `in_reply_to`: parent message ref, usually `msg-<id>`.
- `correlation_id`: reply cycle or obligation key.
- `to_agent_ids`: agents explicitly targeted by the reply.
- `requires_response_by`: optional deadline.
- `reply_contract_version`: `thread_reply.v1` in `metadata_json`.
- `reply_kind`: `agent_reply`, `agent_request`, `agent_followup`, or
  `synthesis`.
- `reply_obligations`: projection of open/answered/cancelled/timed-out
  response obligations.

`squad_reply_obligations` is additive. Rollback is safe by ignoring or dropping
that table; the thread still renders as a flat transcript through
`squad_messages`.

## Behavior

- Operators and agents may reply inside an open thread.
- Targeted replies create one obligation per target agent.
- Agents can call peers only when the target is an active participant in the
  same thread.
- The default reply deadline is 10 minutes.
- Limits are fail-closed: max depth 6, max 20 open obligations per thread, and
  max 2 follow-ups per obligation.
- The coordinator is the only actor allowed to finalize `squad_synthesize`.
- If no coordinator exists, the system records `reply.synthesis_blocked`.

## Tools

- `squad_reply`: canonical reply writer.
- `squad_request_input`: asks one or more peers for contribution.
- `squad_follow_up`: records a bounded follow-up on an open obligation.
- `squad_synthesize`: coordinator-only final response.

All tools remain write tools and pass through ToolRegistry, ExecutionPolicy,
approval, audit, and RunGraph-compatible event paths.

## Observability

Audit/metric events:

- `squad.reply.obligation_created`
- `squad.reply.obligation_resolved`
- `squad.reply.followup_sent`
- `squad.reply.timeout`
- `squad.reply.policy_denied`
- `squad.reply.synthesis_created`

SSE events:

- `reply_added`
- `reply_obligation_updated`
- `synthesis_created`

RunGraph-compatible node types:

- `squad_reply`
- `agent_request`
- `agent_followup`
- `reply_obligation`
- `coordinator_synthesis`

The recurring squad smoke fixture validates mention routing, reply obligation,
child run or task result, coordinator synthesis, partial timeout, and RunGraph
completeness evidence.

## Handoffs And Synthesis Gate

P4/P5 adds `handoff_event.v1` without changing the canonical storage model:
handoffs are transcript-visible `squad_messages` `system_event` rows. They can
target one destination or multiple destinations for parallel consult, and they
carry reason, context policy, deadline, return criteria, status, correlation id,
and RunGraph node id.

Coordinator synthesis now passes through `synthesis_readiness.v1`. The gate
blocks final synthesis while room tasks, reply obligations, child runs, or
handoffs are still open. Terminal declined, failed, cancelled, or timed-out work
is allowed only when the final response explicitly declares the affected
agents/work items.

See [Handoffs, Route Quality, And Synthesis Readiness](handoffs-squad-intelligence.md)
for the full P4/P5 contract.
