# Runtime Architecture

The runtime is the part of Koda that turns a configured agent into observable work: queued tasks, provider execution, tool calls, artifacts, task rooms, and audit records.

## Execution Flow

```text
Incoming request
  -> handler or dashboard route
  -> queue manager
  -> runtime context
  -> memory + knowledge + artifacts
  -> provider CLI / adapter
  -> runtime tool loop
  -> persisted result
  -> calling surface
```

## Main Responsibilities

- Normalize requests from Telegram, dashboard-originated turns, schedules, and internal jobs.
- Resolve the active agent configuration published by the control plane.
- Build prompt, provider, memory, knowledge, and artifact context.
- Execute provider turns and tool calls under policy.
- Record tasks, runtime events, execution traces, costs, artifacts, and audit history.
- Expose live state through `/api/runtime/*` and the dashboard runtime room.

## Worker Supervision

```text
control-plane supervisor
  sends desired active agents to
runtime-kernel
  spawns / terminates
agent worker processes
  expose
/health and /api/runtime/*
```

The runtime-kernel is the OS-level parent for workers. In Docker deployments it includes the Python runtime, Koda package, provider CLIs, shared volumes, and browser/runtime dependencies needed to host those workers.

Both `app` and `runtime-kernel` install the provider CLIs from one lockfile (`packages/provider-clis`) at exact versions. A runner checks the installed CLI against its contract (`koda/services/provider_cli_contract.py`) before the first turn and refuses to build a command line with an option outside it; an unverified CLI makes that provider unavailable. See [Provider CLI versions](../operations/upgrade.md#provider-cli-versions).

## Runtime Room Data

The dashboard runtime view is built from:

- `tasks`
- `runtime_queue_items`
- `runtime_environments`
- `runtime_events`
- `runtime_artifacts`
- `runtime_resource_samples`
- `execution_episodes`
- `audit_events`

These records also power executions, sessions, costs, DLQ views, and documentation demo screenshots.

## Failure Behavior

- Hard security checks fail closed.
- Memory and retrieval are best-effort unless the active policy requires them.
- Runtime mutations are blocked in protected phases.
- Failed or retryable work is visible through executions, task rooms, schedules, and DLQ surfaces.
- `/health`, `/api/runtime/readiness`, and doctor tooling should explain degraded state before operators need logs.
