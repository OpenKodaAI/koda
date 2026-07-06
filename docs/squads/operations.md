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
   counts, dead-letter rows, Telegram retry counts, and SSE client count.
6. Promote more workspaces only after no unauthorized access, duplicate run, or
   dead-letter growth is observed.

For dense multi-agent deployments, size Postgres connections explicitly. The
Postgres bus defaults to `pool_min_size=0` to avoid idle connection fan-out. If
the supervisor/API process owns LISTEN fan-out or the deployment is behind a
pooler that does not support LISTEN, set `SQUAD_BUS_LISTEN_ENABLED=false` and
rely on the bus polling interval.

## Required Validation

Use a real Postgres instance before enabling the Postgres bus:

```bash
POSTGRES_TEST_DSN=postgresql://koda:koda@127.0.0.1:55432/koda \
KNOWLEDGE_V2_POSTGRES_DSN=postgresql://koda:koda@127.0.0.1:55432/koda \
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
- Let a claimed task exceed `SQUAD_CLAIM_TTL_S`; router must return it to
  `pending` and emit `claim_expired`.
- Exceed 80% and then 100% of a thread budget; router must emit alert and
  auto-pause the thread.
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
