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
| System settings | global defaults, system settings, general settings, global secrets, and persistence diagnostics |
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

WebSocket routes:

- `GET /ws/runtime`
- `GET /ws/runtime/events`
- `GET /ws/runtime/tasks/{task_id}/terminals/{terminal_id}`
- `GET /ws/runtime/tasks/{task_id}/browser`

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
