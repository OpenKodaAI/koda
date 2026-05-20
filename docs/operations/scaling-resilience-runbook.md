# Scaling And Resilience Runbook

This runbook is the KG-14 operational contract for the top-tier roadmap. It
defines how Koda must behave under concurrency, partial failure, degraded
dependencies, and operator-facing errors.

Phase 0 does not tune production defaults. It freezes the budgets and gates that
later phases must satisfy before they close.

## Existing Controls To Preserve

| Control | Current source | Phase 0 requirement |
|---|---|---|
| Task leases | `koda/state/history_store.py` | No task may run twice in parallel; tests must prove single-owner acquisition. |
| Lease janitor | `koda/services/queue_manager.py` | Expired tasks must become terminal or recoverable with audit visibility. |
| DLQ | `koda/state/history_store.py` and dashboard DLQ | Irrecoverable failures must be inspectable and retry eligibility must be visible. |
| Circuit breakers | `koda/services/resilience.py` | External dependency failure must degrade explicitly instead of blocking all work. |
| Prometheus metrics | `koda/services/metrics.py` | Queue, active task, request, dependency, breaker, cost, and tool metrics must stay intact. |
| Runtime events | `koda/services/runtime/events.py` | Runtime UI must have enough events to explain progress, stall, retry, and cleanup. |
| Runtime fetch timeout | `apps/web/src/lib/runtime-api.ts` | Frontend fetches should not hang indefinitely; timeout errors need actionable text. |

## Deployment Profiles

| Profile | Target | Required budgets |
|---|---|---|
| Local/dev | 1 operator, 2 agents, 3 concurrent active tasks. | No infinite loading; runtime/control-plane fetch timeout remains 10s unless explicitly changed; smoke runtime passes. |
| Team self-hosted | 5 users, 10 agents, 25 queued tasks per user cap, 8 active standard tasks target. | p95 dashboard JSON API under 1.5s and p99 under 3s, excluding LLM/provider work; recovery after worker restart; SSE reconnect or fallback snapshot. |
| Company self-hosted | Higher concurrency defined per phase before implementation. | Load test proves no double-run, no starvation, explicit backpressure, breaker/degraded mode, DLQ visibility, and cleanup. |

Preserve these current defaults unless a later phase changes them deliberately:

| Default | Value |
|---|---|
| Task lease duration | 60s |
| Task lease heartbeat | 15s |
| Task lease janitor interval | 30s |
| Global max concurrent tasks | 10 |
| Per-user max concurrent tasks | 3 |
| Max queued tasks per user | 25 |
| Runtime/control-plane frontend fetch timeout | 10s |

## Invariants

- No task runs twice in parallel by accident.
- Every task reaches a terminal state or a recoverable state.
- Every external call has timeout, breaker, cancellation path, or explicit
  fallback.
- Backpressure is explicit; queues and fan-out are bounded.
- Retries are idempotent or guarded by policy/approval.
- User-facing errors are typed, actionable, and visible in the UI.
- Resources are bounded and released.
- Observability is part of the product contract.

## Validation Gates

| Gate | Required scenarios | Expected evidence |
|---|---|---|
| Load / concurrency | Multiple users, agents, and tasks; single-owner lease race; queue limit; fair scheduling. | Marked `bench` or focused integration test plus before/after metrics. |
| Fault injection | Provider timeout, MCP hung, browser unavailable, Postgres unavailable, worker restart, lost lease, SSE disconnect. | Marked `chaos` tests or E2E fixture showing recovery/degraded UI. |
| Resource leaks | Ports, processes, browser sessions, worktrees, runtime environments, and temp files on success/fail/cancel/restart. | Tests or smoke logs showing cleanup events and no retained active resources. |
| Error feedback | `queued`, `running`, `retrying`, `stalled`, `degraded`, `failed`, `cancelled`, `completed`. | UI/component/E2E assertion that state, cause, and next action are visible. |
| Security / deny | Non-idempotent write retry, unsafe mount, secret exposure, policy denied tool, unknown-risk MCP. | Fail-closed tests with audit/metric assertion. |
| Observability / replay | Queue wait, lease, dependency call, breaker, retry, DLQ, cancellation, cleanup, user-facing error. | Audit/metric/RunGraph-node declaration and snapshot or integration assertion. |
| P6 ops benchmark | Queue/runtime/channel quick path, timeout, DLQ, backpressure, cleanup. | `ops_benchmark.v1` JSON from `scripts/ops_benchmark.py`; full mode is opt-in with `KODA_OPS_BENCH_FULL=1`. |

## Required Commands

Focused Phase 0 and resilience checks:

```bash
pytest tests/test_services/test_queue_manager_lease.py \
  tests/test_services/test_queue_resilience.py \
  tests/test_services/test_queue_ops_benchmark.py \
  tests/test_services/test_resilience.py \
  tests/test_services/test_global_semaphore.py \
  tests/test_services/runtime/test_recovery_manager.py \
  tests/test_services/runtime/test_events_broker.py
```

P6 quick benchmark:

```bash
uv run python scripts/ops_benchmark.py --json
```

Full deterministic benchmark:

```bash
KODA_OPS_BENCH_FULL=1 uv run python scripts/ops_benchmark.py --json
```

Quick mode is the default CI gate. Full mode is opt-in and should be used before
claiming load/fault robustness for a release train.

Phase closeout checks for broad changes:

```bash
ruff check .
ruff format --check .
mypy koda/ --ignore-missing-imports
pytest --cov=koda --cov-report=term-missing
pnpm lint:web
pnpm test:web
pnpm build:web
```

Rust checks when a phase touches the runtime kernel, command guard, policy
engine, or generated Rust integration:

```bash
cargo fmt --manifest-path rust/Cargo.toml --all --check
cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml --workspace
```

## Operations UI Requirements

Operational UI must answer these questions without requiring logs first:

- What is queued, running, retrying, stalled, degraded, failed, cancelled, or
  completed?
- Which dependency is unavailable or degraded?
- Is the task retryable, already in DLQ, or blocked by policy?
- What action can the operator take: retry, cancel, inspect trace, open DLQ,
  edit approval, run doctor, reconnect runtime, or read troubleshooting?
- What was the last event time, lease owner, attempt count, and cleanup status
  when available?

## Rollback And Migration Rules

- Phase 0 itself should not introduce database migrations or product behavior
  changes.
- Any later migration must have a rollback plan that preserves runs, approvals,
  MCP grants, skill provenance, traces, and runtime artifacts.
- Optimizations that remove trace, bypass policy, or hide user-facing feedback
  are rejected even if they improve raw throughput.
- If a validation gate cannot run, the phase closeout must record the exact
  blocker and the smallest follow-up needed to make the gate executable.
