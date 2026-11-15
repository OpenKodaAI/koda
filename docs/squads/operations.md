# Squads Operations

Squads ship behind two defaults:

```bash
SQUADS_ENABLED=false
INTER_AGENT_BUS_BACKEND=memory
```

Production rollout should be canary-first:

1. Run migrations against Postgres.
2. Enable `SQUADS_ENABLED=true` for one workspace.
3. Keep `INTER_AGENT_BUS_BACKEND=memory` while validating Web and Telegram
   command surfaces.
4. Switch the canary workspace to `INTER_AGENT_BUS_BACKEND=postgres`.
5. Watch inbox depth, delivery attempts, delegation latency, router sweep
   counts, dead-letter rows, Telegram retry counts, and SSE client count. A
   delegator in another process reads its result only from Postgres, so a
   result the bus could not write is logged as
   `delegation_result_persist_failed`, with its `request_id`.
6. Promote more workspaces only after no unauthorized access, duplicate run, or
   dead-letter growth is observed.

For dense multi-agent deployments, size Postgres connections explicitly. The
Postgres bus defaults to `pool_min_size=0` to avoid idle connection fan-out. If
the supervisor/API process owns LISTEN fan-out or the deployment is behind a
pooler that does not support LISTEN, set `SQUAD_BUS_LISTEN_ENABLED=false` and
rely on the bus polling interval. A pooler must also forward the `search_path`
startup parameter the workers send (for PgBouncer, `track_extra_parameters`; see
[Postgres settings](../config/reference.md#postgres)).

## Required Validation

Use a real Postgres instance before enabling the Postgres bus:

```bash
POSTGRES_TEST_DSN=postgresql://koda:koda@127.0.0.1:55432/koda \
uv run pytest -m postgres -q
```

The suite covers message leasing, `ack`/`nack`, dead-lettering, delegation
resolution by correlation id, task CAS, projections, router sweeps, and access
boundaries.

Run the normal release checks after the Postgres pass:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy koda/ --ignore-missing-imports
uv run pytest --cov=koda --cov-report=term-missing
pnpm lint:web
pnpm test:web
pnpm build:web
```

## Telegram Canary

Validate one real supergroup before opening access:

1. Create a supergroup and enable forum topics.
2. Add all squad bots as admins.
3. Keep `SQUAD_TELEGRAM_STRICT_ADMIN_CHECK=true`.
4. Run `/squad_bind <workspace_id> <squad_id>`.
5. Run `/squad_thread_new <title>`.
6. Post a user message, an explicit `@agent-id`, and a reply continuation.
7. Confirm replies land in the same `message_thread_id` and are debounced when
   several agents answer within `SQUAD_DEBOUNCE_MS`.

## Failure Drills

Before broad rollout, run these in canary:

- Kill a worker after receive but before ack; the message must replay after
  lease expiry.
- Kill a worker after enqueue and ack; idempotency must prevent duplicate runs.
- Force a provider timeout; router must emit sanitized `run_failed` or
  `task_result(status=failed)`.
- Let a claimed task exceed `SQUAD_CLAIM_TTL_S` with no runtime holding its
  turn; router must return it to `pending` with its planned assignee kept,
  emit `claim_expired`, and dispatch the task to that assignee again. When the
  claim expires a second time the router escalates the task: the system posts
  a failed `task_result` that says so, the task ends `escalated`, and the
  coordinator synthesis discloses it. A runtime renews the claim of each task
  whose turn it has queued or is running on every router sweep, so a turn that
  waits or runs longer than the TTL is neither dispatched twice nor escalated.
  A squad turn requeued from the dead-letter queue stays a squad turn, and its
  claim is renewed the same way. Claims of a paused or spent thread wait until
  it is open again.
- Exceed 80% and then 100% of a thread budget; router must emit alert and
  auto-pause the thread (`budget_exceeded_auto_pause`, reason `budget`), one
  event per pause. A room reopened at its cap is paused again, with a new
  event; one reopened under its cap is no longer marked as paused by the
  budget, and a later overrun pauses it again. Paused rooms already alerted
  do not keep the sweep from an open room at its cap.
  A thread that is not `open`, or whose spend reached its cap, runs no agent
  turn on any path: web, Telegram, the inbox, unblocked tasks or synthesis,
  and the queue worker checks again when it takes a queued or recovered turn.
  A thread the worker or the queue cannot read runs no turn either. When the
  worker's read of a queued turn's thread fails, it takes the turn again
  after 2, 5, 15, 30 and 60 seconds before it refuses it; a thread that does
  not exist refuses the turn at once, and a runtime API squad message to it
  gets 404 (one to a paused or spent thread gets 409). When the queue worker
  refuses a queued turn, or the unblocked-task follow-ups, the inbox or the
  router's dispatch of a task whose claim expired are refused a task's turn,
  whichever read refuses it (the dispatch's own, the local queue's, or the
  runtime API's 409, which no other transport then delivers around),
  the task's claim is released without counting an expiry, so pauses never
  escalate a task, and the first router sweep after the thread is open again
  under its cap dispatches the task again, without waiting for
  `SQUAD_CLAIM_TTL_S` and without a `claim_expired` event. A
  later claim of the task is a live one again: it is renewed, and its expiry
  counts. A coordinator synthesis the room refuses in a cycle with no handoff
  is recorded as one `synthesis_refused` system event, and the first router
  sweep after the room can run again runs it, with the same idempotency key,
  at most once; a handoff cycle's synthesis is retried by the open-handoff
  sweep. A finished task unblocks only the pending tasks of its own
  coordination cycle; a pending task of an earlier cycle is not dispatched.
  A dashboard post or Telegram topic message to such a thread is not routed;
  the sender is told why. A dashboard room update may set only `photo_url` in
  `metadata`; keys the server keeps, such as the budget flags, are refused.
- Pause a room from the dashboard; the room must show a `thread_paused`
  system event with reason `operator`.
- Have agents delegate A to B to C and back to A, delegate past
  `INTER_AGENT_MAX_DELEGATION_DEPTH`, and answer each other with `agent_send`
  past 6 hops (`MAX_REPLY_DEPTH`, the bound `squad_reply` has). Each delegation
  request and `agent_send` message carries the whole chain of agents that led
  to it, ending with its sender, and every entry counts, the router's included.
  A `squad_reply` or synthesis turn keeps the chain on every path that delivers
  it: the local queue, the runtime API and the bus fallback.
  The sender's tool refuses the cycle, the depth or the hop count, and the
  receiving inbox refuses the same before it queues a turn, whichever runtime
  sent it: the inbox adds the sender to a chain that does not end with it, so
  it counts every hop even from a sender that does not add itself. A
  delegator the inbox refuses gets the failure at once. The inbox runs squad
  turns only, so a delegation sent outside a squad thread also fails at once,
  with a reason that says so, instead of waiting for its timeout. Each refusal
  must show one `delegation_limit_reached` system event whose `limit` is
  `cycle`, `depth` or `hop_count`.
- Disable a Telegram bot admin permission; bind/strict checks must fail closed.

## Rollback

Rollback is flag-based:

```bash
SQUADS_ENABLED=false
INTER_AGENT_BUS_BACKEND=memory
```

Existing squad rows remain in Postgres for audit/replay. Do not delete
`squad_messages` or `squad_message_recipients` during rollback; pending rows
can be replayed after the feature is re-enabled.
