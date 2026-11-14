# API Reference

Koda exposes three HTTP surfaces:

- the **control-plane API** on `/api/control-plane/*`
- the **runtime inspection/control API** on `/api/runtime/*` plus runtime WebSockets
- small public probes and compatibility pages such as `/health`, `/setup`, and `/openapi/control-plane.json`

The maintained OpenAPI contract is:

- [`../openapi/control-plane.json`](../openapi/control-plane.json)

At this revision, that OpenAPI document mirrors every operator-facing route registered in `koda/control_plane/api.py`, plus `/health` and the runtime readiness probe. Dynamic dashboard bundle routes intentionally use broad schemas instead of invented field-level contracts; the field-level truth for those lives in the server handler and dashboard contract files.

## Authentication

Most control-plane routes require one of:

- the operator session cookie created by `/api/control-plane/auth/login`
- a bearer token created by `/api/control-plane/auth/tokens`
- the break-glass `CONTROL_PLANE_API_TOKEN`, when configured

Public or bootstrap routes are explicitly marked with `security: []` in the OpenAPI. Auth-adjacent routes are rate-limited more strictly than normal operator routes.

## Control Plane

The control plane owns product configuration and operator-facing management. The OpenAPI includes these route groups:

| Group | Route families |
| --- | --- |
| Setup and onboarding | `/setup`, `/api/control-plane/onboarding/*`, `/api/control-plane/auth/bootstrap/*` |
| Auth and account | `/api/control-plane/auth/status`, login/logout, profile, profile photo, password recovery/change, recovery codes, sessions, API tokens |
| Core catalogs | `/api/control-plane/core/providers`, `/core/tools`, `/core/policies`, `/core/capabilities` |
| Dashboard bundles | `/api/control-plane/dashboard/*` for summaries, rooms, squads, sessions, executions, approvals, DLQ, costs, schedules, memory curation, link previews, and artifacts |
| Agents | agent CRUD, clone, publish, activate/pause, runtime access, agent spec, compiled prompt, validation, publish checks, policies, sections, documents, knowledge assets, templates, skills, secrets, Telegram bot info |
| Workspaces and squads | workspace CRUD, directory roots/list/scan/import, workspace spec, squad spec, squad creation/update/delete |
| Memory, knowledge, and evals | knowledge candidates, runbooks, retrieval/answer traces, knowledge graph, legacy knowledge evals, `eval_case.v1`, eval runs, trajectory exports, latest release quality |
| Self-improvement | `improvement_proposal.v1` list/create/detail plus approve, reject, validate, apply, and rollback |
| Quality cockpit | quality overview, per-agent quality, and failure-to-proposal |
| Providers | provider connection state, API-key/local/subscription-login flows, verification, disconnect, Ollama, ElevenLabs, Kokoro, Supertonic, Whisper, embedding model downloads/select/delete, active download jobs, and cancellation |
| System settings | global defaults, system settings, general settings, global secrets, placeholder-secret status (names only, for the dashboard warning banner), and persistence diagnostics |
| Channel gateway | `channel_gateway.v1` state, pairing codes, unknown senders, approve, block, revoke |
| Connections and MCP | system defaults, per-agent connections, tool discovery/policies, OAuth start/status/refresh/revoke, resources, prompts, capability policies, MCP catalog, custom MCP servers, and Claude Desktop MCP import |

## Runtime API

The runtime API powers the dashboard's live operational rooms. It is not published as a separate OpenAPI document; use this inventory together with `koda/services/runtime/api.py` and the dashboard runtime contracts.

Read routes:

- `GET /api/runtime/readiness`
- `GET /api/runtime/queues`
- `GET /api/runtime/environments`
- `GET /api/runtime/environments/{env_id}`
- `GET /api/runtime/schedules`
- `GET /api/runtime/schedules/{job_id}`
- `GET /api/runtime/tasks/{task_id}`
- `GET /api/runtime/tasks/{task_id}/run-graph`
- `GET /api/runtime/tasks/{task_id}/replay`
- `GET /api/runtime/tasks/{task_id}/sandbox-doctor`
- `GET /api/runtime/tasks/{task_id}/events`
- `GET /api/runtime/tasks/{task_id}/artifacts`
- `GET /api/runtime/artifacts/{artifact_id}/download`
- `GET /api/runtime/tasks/{task_id}/checkpoints`
- `GET /api/runtime/tasks/{task_id}/terminals`
- `GET /api/runtime/tasks/{task_id}/browser`
- `GET /api/runtime/tasks/{task_id}/browser/screenshot`
- `GET /api/runtime/tasks/{task_id}/workspace/tree`
- `GET /api/runtime/tasks/{task_id}/workspace/file`
- `GET /api/runtime/tasks/{task_id}/workspace/search`
- `GET /api/runtime/tasks/{task_id}/workspace/status`
- `GET /api/runtime/tasks/{task_id}/workspace/diff`
- `GET /api/runtime/tasks/{task_id}/services`
- `GET /api/runtime/tasks/{task_id}/resources`
- `GET /api/runtime/tasks/{task_id}/loop`
- `GET /api/runtime/tasks/{task_id}/sessions`
- `GET /api/runtime/stream`

Write/control routes:

- `POST /api/runtime/schedules`
- `PATCH /api/runtime/schedules/{job_id}`
- `POST /api/runtime/schedules/{job_id}/actions/{action}`
- `POST /api/runtime/sessions/messages`
- `POST /api/runtime/sessions/{session_id}/cancel`
- `POST /api/runtime/sessions/{session_id}/pause`
- `POST /api/runtime/sessions/{session_id}/resume`
- `POST /api/runtime/tasks/{task_id}/cancel`
- `POST /api/runtime/tasks/{task_id}/interrupt`
- `POST /api/runtime/tasks/{task_id}/retry`
- `POST /api/runtime/tasks/{task_id}/recover`
- `POST /api/runtime/tasks/{task_id}/pause`
- `POST /api/runtime/tasks/{task_id}/resume`
- `POST /api/runtime/tasks/{task_id}/save`
- `POST /api/runtime/tasks/{task_id}/attach/terminal`
- `POST /api/runtime/tasks/{task_id}/attach/browser`
- `POST /api/runtime/tasks/{task_id}/pin`
- `POST /api/runtime/tasks/{task_id}/unpin`
- `POST /api/runtime/tasks/{task_id}/cleanup`
- `POST /api/runtime/tasks/{task_id}/cleanup/force`
- `POST /api/runtime/tasks/{task_id}/workspace/write`
- `POST /api/runtime/tasks/{task_id}/workspace/create`
- `POST /api/runtime/tasks/{task_id}/workspace/delete`
- `POST /api/runtime/tasks/{task_id}/workspace/rename`
- `POST /api/runtime/processes/{process_id}/terminate`

`POST /api/runtime/schedules` creates the job in `validation_pending` and queues a dry-run validation run, returned as `validation_run_id` with a `message`. When `auto_activate` is true (the default) a passing validation activates the job; otherwise the job stays `validated` until the `activate` or `resume` action is called. A failed validation leaves the job `failed_open`. `run` is rejected until the job has been validated. If the validation could not be queued the job is still created (`201`), but `validation_run_id` is `null` and `message` says why; call the `validate` action to retry it. A replay with the same `X-Idempotency-Key` returns the original `message` and `validation_run_id`. The `validate` action itself answers `400` with `{"ok": false, "message": ...}` when it is refused, for example while a validation run is still pending.

Automatic (scheduled and catch-up) runs follow the agent's current policy rather than the snapshot captured at validation: when the job's stored policy snapshot is stale, the dispatcher refreshes it before materializing runs and records a `job.policy_snapshot_refreshed` event with the previous and new `policy_snapshot_hash`.

`payload.read_only` and `payload.allowed_paths` are stored with the job but are not enforced yet: a run is not stopped from writing and is not limited to those paths. `read_only: true` only pins `safety_mode` to `dry_run_required`, which is already the default. The dashboard routine editor labels both settings "Not enforced yet", does not set them on new routines, and leaves the values an existing routine stores unchanged when it is edited.

`POST /api/runtime/tasks/{task_id}/cancel` and `/interrupt` stop a task that is queued, running, or
retrying and return `action: "cancelled"` (or `"interrupted"`) with its `final_phase`. A task without a
runtime environment that has already finished (for example completed, failed, cancelled, or
`needs_review`) is left as it is: the route answers `409` with `error`, `action: "not_running"`,
`ok: false`, its `status`, and its unchanged `final_phase`.

WebSocket routes:

- `GET /ws/runtime`
- `GET /ws/runtime/events`
- `GET /ws/runtime/tasks/{task_id}/terminals/{terminal_id}`
- `GET /ws/runtime/tasks/{task_id}/browser`

### Event stream resume

`GET /api/runtime/stream`, `GET /ws/runtime`, `GET /ws/runtime/events`, and `GET /api/runtime/tasks/{task_id}/events` accept `after_seq`, a resume cursor. Each event's `seq` is the agent-wide `runtime_events` id, so the cursor keeps growing across tasks. Clients reconnect with the highest `seq` they received. `after_seq` accepts any integer from `0` to `9223372036854775807`. A missing value means `0`. A value that is not an integer or is out of range returns `400` (`invalid after_seq`).

The stream and WebSocket routes also accept the optional filters `task_id` and `env_id`, in the same integer range. An invalid filter returns `400` (`invalid task_id`, `invalid env_id`). All of these parameters are checked before the stream starts or the WebSocket is upgraded, so an invalid request gets a `400` instead of an empty stream.

The dashboard relays (`/api/runtime/agents/{agentId}/stream` and `/api/runtime/agents/{agentId}/sessions/{sessionId}/stream`) treat failures in two ways:

- A transient failure gets a non-`200` JSON error, so the browser `EventSource` fails without opening and the dashboard reconnects with its normal backoff. Every runtime status other than `400`, `404`, and `422` is transient, for example `401`, `403`, `408`, `429`, and `5xx`. An unreachable runtime and any failure before the runtime answers are transient too. A `401` or `403` usually means the relay could not get a runtime token from the control plane. A failure before the runtime answers includes a control plane that is unavailable, which the relay reports as `Agent not found` (`404`) because it cannot tell the two cases apart.
- A request the runtime itself rejected (`400`, `404`, or `422`) is delivered as one `stream_error` event on a `200` event stream, with data `{"status": <code>}`. The relay does not forward the runtime's error message. `EventSource` cannot read HTTP statuses, which is why the relay sends the rejection as an event. The dashboard hooks then wait 60 seconds before they try again, instead of a few seconds. The pages keep polling for updates until the stream reconnects.

## Status And Errors

Stable operator-facing failures should use Koda's operational error envelope where the boundary has been formalized:

```json
{
  "error": {
    "code": "runtime.dependency_timeout",
    "category": "timeout",
    "message": "Runtime dependency timed out.",
    "retryable": true,
    "user_action": "Retry the task or inspect dependency health."
  }
}
```

Common HTTP statuses:

- `200` / `201` / `202`: successful synchronous or accepted asynchronous work
- `400`: invalid request body or invalid transition
- `401`: missing or invalid operator session/token
- `403`: authenticated but not allowed, policy denied, or fail-closed guard
- `404`: unknown route, agent, task, session, resource, or artifact
- `409`: conflict, duplicate, or invalid lifecycle state
- `429`: rate-limited auth or operator request
- `500` / `503`: unexpected product error or dependency unavailable

## Stability

- The OpenAPI file is the source of truth for the maintained control-plane HTTP contract.
- Runtime HTTP and WebSocket routes are stable dashboard-facing operational surfaces, but do not currently ship as a separate OpenAPI document.
- Internal gRPC contracts, provider CLI behavior, and Rust sidecar APIs are intentionally outside this public HTTP contract.
- Routes backed by broad OpenAPI schemas are still real routes; the broad schema means the response is a server/dashboard bundle rather than a promised client SDK model.
