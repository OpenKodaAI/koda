# Thread Replies Runbook

Use thread replies when a Squad Room needs explicit agent-to-agent coordination
before the coordinator answers the user.

## Operator Flow

1. Open a room in Sessions.
2. Hover a message and choose Reply.
3. If the parent was authored by an agent, the composer targets that agent by
   default.
4. Send the reply. The backend creates a `thread_reply.v1` message and an open
   obligation for each target.
5. Watch the right-side Thread panel for waiting/answered states.
6. The coordinator synthesizes the final response after required replies close.

## Agent Flow

Agents can use:

- `squad_request_input` to ask a peer for a missing contribution.
- `squad_reply` to answer or create a targeted reply.
- `squad_follow_up` to send at most two follow-ups for an open obligation.
- `squad_synthesize` when the current agent is the coordinator and the final
  answer is ready.

## Failure Modes

- `reply.parent_not_found`: parent message or thread does not exist.
- `reply.target_not_participant`: target is not an active room participant.
- `reply.policy_denied`: thread status, limits, or policy blocked the action.
- `reply.loop_detected`: reply depth exceeded the configured cap.
- `reply.deadline_exceeded`: obligation timed out.
- `reply.synthesis_blocked`: no coordinator or non-coordinator attempted final
  synthesis.

## Rollback

No existing transcript data is rewritten. To roll back, disable the new tools
or ignore/drop `squad_reply_obligations`. Messages remain visible through the
legacy flat `squad_messages` timeline.

## Smoke Gate

Recurring squad validation:

```bash
python scripts/squad_smoke.py --input tests/fixtures/evals/squad_smoke.v1.json
```

The fixture must include mention routing, an open/resolved reply obligation, a
child run or task result, coordinator synthesis, partial timeout evidence, and a
passing `run_graph_completeness.v1` report.
