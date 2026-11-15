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

Public or bootstrap routes are explicitly marked with `security: []` in the OpenAPI; `tests/test_control_plane_auth_matrix.py` checks the OpenAPI security of every operation against what its route does without a session. `GET /api/control-plane/onboarding/status` is public with an optional bearer (`security: [{}, {"bearerAuth": []}]`): without a credential it returns only `has_owner` and `bootstrap_required`; see [`../security/authentication.md`](../security/authentication.md). Auth-adjacent routes are rate-limited more strictly than normal operator routes.

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
| Self-improvement | `improvement_proposal.v1` list/create/detail plus approve, reject, validate, apply (accept, recorded only: it does not change the agent), and rollback |
| Quality cockpit | quality overview, per-agent quality, and failure-to-proposal |
| Providers | provider connection state, API-key/local/subscription-login flows, verification, disconnect (runs `claude auth logout` or `codex logout` where the CLI is installed, removes the stored key and only the CLI's credential files, with the temp copies a CLI writes some of them through and can leave behind — Claude `.credentials.json`, Codex `auth.json`, `.credentials.json`, `secrets/gateway_oauth.json`, `secrets/codex_auth.age`, `secrets/mcp_oauth.age`, `secrets/gateway_oauth.age`, Gemini `oauth_creds.json`, `google_accounts.json`, `mcp-oauth-tokens.json`, `a2a-oauth-tokens.json`, the last three also in `~/.cache/.gemini/` where Gemini runs in the macOS sandbox, and the sign-ins in Gemini's encrypted file keychain `gemini-credentials.json`, keeping its other entries and deleting a keychain that held only sign-ins — and resets the connection to its fresh-install mode; Claude's `.credentials.json` also holds the MCP OAuth client secrets entered with `claude mcp add --client-secret`, which `claude auth logout` deletes with it too), Ollama, ElevenLabs, Kokoro, Supertonic, Whisper, embedding model downloads/select/delete, active download jobs, and cancellation |
| System settings | global defaults, system settings, general settings, global secrets, placeholder-secret status (names only, for the dashboard warning banner), and persistence diagnostics |
| Channel gateway | `channel_gateway.v1` state, pairing codes, unknown senders, approve, block, revoke |
| Connections and MCP | system defaults, per-agent connections, tool discovery/policies, OAuth start/status/refresh/revoke, resources, prompts, capability policies, MCP catalog, custom MCP servers, and Claude Desktop MCP import |

### Execution-policy simulator

`POST /api/control-plane/agents/{agent_id}/execution-policy/evaluate` evaluates one tool call with the same engine the agent's worker uses (`koda/services/execution_policy.py`). The body is `{"action": {"tool_id": "...", "params": {...}, "task_kind": "general"}, "policy": {...}}`. The worker derives the action envelope (integration, action, access level, effect tags, path, domain) from `tool_id` and `params`, so the simulator does too: other envelope fields in `action` are ignored. `policy` is optional and defaults to the agent's draft execution policy. The agent's tool, resource-access and autonomy policies and its MCP tool policies apply as they do in its worker, and so do its worker's feature flags (browser, shell, fileops and the others), which the simulator derives as `koda/config.py` does in the worker, not from the control-plane process's own settings: from the environment the supervisor gives the worker, that is the agent's environment, where a setting's agent-scoped `<AGENT_ID>_<KEY>` entry comes first, with the supervisor's own `INTER_AGENT_ENABLED` applying only when the agent's environment does not set it, and then from the install's `.env` file, which `koda/config.py` loads without override, so it fills only the keys (`<AGENT_ID>_<KEY>` ones included) that environment lacks, unless the environment sets `PYTHON_DOTENV_DISABLED` (`${VAR}` expansion inside the file is not simulated); the task policy is the default for `task_kind` (default `general`). A tool is known when the worker's tool dispatcher has a handler for it or it is an MCP tool; the simulator and the worker use the same check (`koda.agent_contract.is_known_dispatcher_tool`), and any other tool is denied as `unknown_action`. The one gap is plugin tools: the control plane cannot see a worker's plugin registry, so the simulator denies them as `unknown_action`, while a worker that has loaded the plugin evaluates them. The response carries `agent_id`, the normalized `policy`, `catalog`, `action`, and `evaluation` with `decision`, `reason_code`, `reason`, `rule_id`, `matched_selector`, `approval_scope`, `preview_text`, `envelope` and `requires_confirmation`.

Rule semantics: among the rules that match a call, the most restrictive decision wins (`deny` > `require_approval` > `allow_with_preview` > `allow`), then the highest `priority`, then the lowest `name`; the winning rule's `name` is the `rule_id` recorded in audit. Selector values are fnmatch patterns (`*`, `?`, `[seq]`), compared case-insensitively, and `effect_tags` needs every listed pattern to match a tag. A `path` selector also covers everything below that path. For `file_search`, `file_grep` and both ends of `file_move`, which act on everything below their path, a `deny`, `require_approval` or `allow_with_preview` path rule also matches when its path lies below the call's path (in any of the spellings below), so a search, grep or move of an ancestor of the rule's directory does not step around it; a rule path with a wildcard segment counts when the call's path is at, above or below the segments before the wildcard, and one that starts with `*` always counts. The engine cannot tell whether a move's source is a directory, so every `file_move` counts as a directory move: a restrictive rule below either end, or one that starts with `*`, decides a single-file move or rename too (a deny for `*.pem` denies `file_move` of `/srv/work/a.txt` to `/srv/work/b.txt`). For `file_list` and `/ls`, which show the direct entries of their path (name, kind and size) and nothing deeper, such a rule also matches when its path can be one of those entries: a rule path without a wildcard that is a direct entry of the call's path, one with a wildcard segment whose fixed part is the call's path or above it, and one that starts with `*`; a rule for a path deeper than the entries does not decide the listing. An `allow` path rule must cover the call's path itself. Path rules are evaluated against these paths (`koda.agent_contract.resolve_action_paths`): a `file_*` tool's `path`, `source` and `destination` (so both ends of a `file_move`); the working directory for `file_list`, `file_search` and `file_grep` called without a `path`; the `path` of an `agent_*` tool (`agent_set_workdir`); and the path an operator file command acts on, which is the first argument of `/write` and `/edit` and the whole argument string, spaces included, of `/rm`, `/mkdir`, `/cat`, `/file` and `/ls` (the working directory for `/ls` alone), resolved under the operator's work dir as the command resolves it. In the worker, a file tool's `path`, `source` and `destination` reach the rules as the absolute, symlink-resolved path each names under the agent's working directory (`~` expanded with the worker's `HOME`), and the working directory of a `file_list`, `file_search` or `file_grep` without a `path` is the resolved working directory (`koda/services/tool_dispatcher.py::_file_tool_policy_params`, M1-E4-T13); a value that is not a non-blank string or cannot be resolved is passed as written, and the tool then refuses it. The `path` of `agent_set_workdir` is passed as written. This route has no working directory and evaluates `params` as sent. No other param is a path to these rules: an MCP tool's params, `browser_upload`'s `file_path`, `plugin_install`'s `path`, the `path` of `git_diff` and `git_log`, and `job_create`'s `work_dir` are not evaluated, and neither is anything a shell or git command touches, so a path rule does not keep those tools out of a directory (owner: AG-12). An absolute path is evaluated against the whole rule set once for each of its spellings: lexically normalized (`.`, `..` and repeated `/` resolved) and as written, each compared with case and ignoring case. The as-written spelling is the one below a rule's path in a call such as `/srv/work/link/../other/key` against a rule for `/srv/work/link`: when that directory is a symlink, the tool's realpath resolves the link before the `..`, so the call can land wherever the link points. A path that is not absolute (one that starts with `~`, a relative path, the working directory of a call without a `path`, or a path with leading whitespace) cannot be placed by the engine, which knows neither a working directory nor a `HOME`: every `deny`, `require_approval` and `allow_with_preview` path rule counts as matching it, and no `allow` path rule does. In the worker only `agent_set_workdir`'s `path` (and a file-tool value the tool refuses) reaches the engine unplaced; this route evaluates every relative or `~` path, and every `file_list`, `file_search` or `file_grep` without a `path`, this way. The `fileops` grant's `allowed_paths` check sees the same paths (`koda.agent_contract._grant_scoped_paths`), and no `allowed_paths` entry covers a path that cannot be placed, so on this route such a call is outside every path-scoped grant, while the worker checks the resolved path or working directory. So for those calls this route can return a stricter decision than the worker makes, never a looser one. Send the absolute path a call resolves to for the worker's decision. The decision is the most restrictive outcome over all of these evaluations, and an evaluation that no rule matches counts as the no-match fallback (allow for a safe read, deny otherwise); the deciding rule (its `rule_id`, approval scope and preview fields) is then the highest-`priority`, then lowest-`name` rule with that decision that matched any of them. So no `.`, `..`, repeated `/` or other-case spelling, no `~` or relative path and neither end of a move steps around a `deny`, `require_approval` or `allow_with_preview` path rule, and an `allow` path rule covers a call only when it covers each spelling of each of the call's paths, with case. An `approve scope` grant records the same paths, so it covers a later call only when that call acts on the same paths: a grant for one `file_move` does not cover a move from the same source to another destination. Symlinks: the engine does not resolve a call's path, but in the worker a file tool's path reaches it already symlink-resolved by the safe-path resolver (M1-E4-T13), so a link inside a covered directory is evaluated where it points; the simulator evaluates the path as written. A `deny`, `require_approval` or `allow_with_preview` rule's path is also compared with its fixed part (the segments before the first wildcard) symlink-resolved when the call is evaluated, so a rule written through a symlinked directory, such as `/srv/app/config/secrets` with `/srv/app` linking to `/srv/releases/v42`, still decides a call on the resolved path. An `allow` rule's path is compared as written: the agent can repoint a link inside its work dir, and resolving an `allow` rule through it would widen the rule, so an `allow` rule written through a symlink does not cover the resolved paths. A rule's `path` patterns are normalized the same way (`/srv//prod`, `/srv/./prod` and `/srv/x/../prod` all mean `/srv/prod`). Validation (and so publish) rejects a selector the engine cannot evaluate, that is an unknown key, an empty value, a mapping value, a value other than true or false on a boolean selector (`private_network`, `uses_secrets`, `bulk_operation`, `external_side_effect`), a `^regex` pattern, or a `path` pattern that cannot be normalized: one that is neither absolute nor starts with `*` (to match at any depth), such as `~/prod` or `srv/prod`, or one with `..` after a segment with a wildcard, such as `/srv/*/../prod`; it rejects a rule with no selectors or an unknown `decision` (or legacy `action`); and it rejects two rules with the same name (an unnamed rule is named `rule_<index>`). Publish validates the execution policy as stored, and `PUT .../agent-spec` and `PUT .../execution-policy` return 400 with these errors when the policy they write changes and is invalid. If an unevaluable selector is stored anyway, a deny rule ignores it, and any other rule does not match. The normalizer drops a rule with no selectors or an unknown decision, and a rule with no decision means `require_approval`. The shared cases live in `tests/fixtures/execution_policy_vectors.json`.

## Runtime API

The runtime API powers the dashboard's live operational rooms. It is not published as a separate OpenAPI document; use this inventory together with `koda/services/runtime/api.py` and the dashboard runtime contracts.

Every runtime route, including the WebSocket upgrades, needs an `X-Runtime-Token` header. This is a short-lived token that the control plane signs with the agent's `RUNTIME_LOCAL_UI_TOKEN`. It is scoped to one agent and to a capability. The worker compares the token's agent with its own `AGENT_ID`, but it skips this check when either one is empty. A token without an agent scope, or any token sent to a worker started without `AGENT_ID`, passes the agent check. The control plane always signs a token for one agent and the supervisor always sets `AGENT_ID`, so supervised workers are not affected. Set `AGENT_ID` on any worker you start by hand. The control plane issues the token as `runtime_request_token` from `GET /api/control-plane/agents/{agent_id}/runtime-access?capability=read|mutate|attach`, and the dashboard relay fetches it on the server side.

- Read routes and the WebSocket routes need `read`.
- Write and control routes need `mutate`. The two `attach` routes need `attach`.
- The terminal and browser WebSockets also need the attach token that the matching `attach` route returns. Send it in `X-Koda-Attach-Token` or in the `token` query parameter.
- `GET /api/runtime/tasks/{task_id}?include_sensitive=true` also needs a sensitive scope token in `X-Runtime-Access-Scope`. The control plane returns it as `access_scope_token` when you call it with `include_sensitive=true`.

The worker answers `403` to a missing, forged, expired or wrongly scoped token, and to any token when it has no `RUNTIME_LOCAL_UI_TOKEN`. A WebSocket upgrade is refused with `403`. `/health`, `/ready` and `/metrics` on the same port need no token.

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
retrying and return `action: "cancelled"` (or `"interrupted"`) with its `final_phase`. A stopped task
delivers no response and starts no further provider run (no streaming fallback, provider fallback, or
retry), also when its provider exits while the runtime kernel is still stopping it. A task without a
runtime environment that has already finished (for example completed, failed, cancelled, or
`needs_review`) is left as it is: the route answers `409` with `error`, `action: "not_running"`,
`ok: false`, its `status`, and its unchanged `final_phase`.

`POST /api/runtime/sessions/messages` with a `squad` object queues a turn on that squad thread. The worker takes the identity the turn runs as from the thread, not from the request: the thread's `owner_user_id` and `telegram_chat_id`, or an id derived from the session when the thread has none. `squad.user_id`, `squad.chat_id` and `squad.telegram_chat_id` are ignored: the `202` response lists each one sent with a different value in `ignored` (for example `["squad.user_id"]`), and the runtime logs `squad_message_identity_ignored`. A `squad.thread_id` that is not a UUID returns `400`, an unknown thread `404`.

Numeric query parameters (`limit` on `/api/runtime/schedules`; `run_limit`, `run_offset` or `offset`, and `event_limit` on `/api/runtime/schedules/{job_id}`; `after_offset` on the terminal WebSocket; and the stream parameters below) answer a value that is not an integer or is out of range with `400` and `invalid <name>`. A WebSocket route checks them before the upgrade.

The browser payload of the routes named in this paragraph is an explicit projection: only the fields named here are sent, so the kernel's and the session's free-form `metadata` (with its `xvfb_log`, `openbox_log`, `x11vnc_log` and `websockify_log` paths) and any key the kernel adds later are not sent in these payloads. The `browser` object of `GET /api/runtime/tasks/{task_id}/browser` and of `POST /api/runtime/tasks/{task_id}/attach/browser`, and the browser WebSocket's `browser.snapshot` messages, carry `scope_id`, `transport`, `status`, `last_known_status`, `display_id`, `vnc_port`, `novnc_port`, `missing_binaries`, `visual_available`, `session_persisted_only`, `runtime_dir`, `unavailable_reason`, `kernel_error` and `last_title` when the session has them, and `screenshot_url`, `preview_url`, `preview_available` and, when a preview image exists, `preview_path`. The `sessions` rows of `GET .../browser` and the `browser_sessions` rows of `GET /api/runtime/tasks/{task_id}/sessions` carry `id`, `task_id`, `env_id`, `scope_id`, `transport`, `status`, `display_id`, `vnc_port`, `novnc_port`, `created_at`, `updated_at` and `ended_at`. `runtime_dir` and `preview_path` are relative to the task's runtime directory (`<runtime root>/tasks/<task_id>`), for example `browser` or `browser/browser_7_1700000000000.png`, and `null` for a path outside it; these payloads never carry an absolute host path. The text fields `unavailable_reason`, `kernel_error` and `last_title` are returned as they are, also when they start with `/`.

The responses that carry an environment, a terminal or a runtime event are explicit projections too, so none of them sends the runtime root, the state root or a task directory as an absolute path:

- The environment rows of `GET /api/runtime/environments` and `GET /api/runtime/environments/{env_id}`, the `environment` of `GET /api/runtime/tasks/{task_id}`, and the environment the sandbox doctor (`GET /api/runtime/tasks/{task_id}/sandbox-doctor` and the task's `sandbox_doctor`) is built from carry `id`, `task_id`, `user_id`, `chat_id`, `classification`, `environment_kind`, `isolation`, `duration`, `status`, `current_phase`, `branch_name`, `created_worktree`, `worktree_mode`, `is_pinned`, `checkpoint_status`, `parent_env_id`, `lineage_root_env_id`, `source_checkpoint_id`, `recovery_state`, `revision`, `browser_transport`, `display_id`, `vnc_port`, `novnc_port`, `pause_state`, `pause_reason`, `save_verified_at`, `process_pid`, `process_pgid`, `browser_scope_id`, `created_at`, `updated_at`, `last_heartbeat_at`, `retention_expires_at` and `source_root_exists`. Their `workspace_path`, `runtime_dir`, `base_work_dir`, `source_root_path` and `checkpoint_path` are relative to the task's runtime directory: `.` for the directory itself, `checkpoints/1` for a checkpoint in it, and `null` for a path outside it, such as a worktree under `<runtime root>/worktrees` or the agent's work directory.
- The terminal rows of `GET /api/runtime/tasks/{task_id}/terminals`, the `terminals` of `GET /api/runtime/tasks/{task_id}/sessions` and the `terminal` of `POST /api/runtime/tasks/{task_id}/attach/terminal` carry `id`, `task_id`, `env_id`, `terminal_kind`, `label`, `interactive`, `cursor_offset`, `last_offset`, `created_at` and `updated_at`, and `path` and `stream_path` relative to the task's runtime directory (for example `stdout/build.log`), a `kernel://<session>` reference as it is, or `null`.
- Runtime events, as `GET /api/runtime/tasks/{task_id}/events`, `GET /api/runtime/stream`, `GET /ws/runtime` and `GET /ws/runtime/events` return them and as the task's `run_graph` and `run_replay` are built from them, carry `seq`, `ts`, `task_id`, `env_id`, `attempt`, `phase`, `type`, `severity`, `resource_snapshot_ref`, `payload` and `artifact_refs`. Each of `artifact_refs` is relative to the task's runtime directory, and a reference outside it is left out. The `payload` of `browser.started` is the browser projection above; that of `browser.frame`, `browser.video_ready` and `browser.trace_ready` is `{"path": ...}`; `worktree.created` carries `branch_name`, `created`, `mode`, `workspace_path` and `metadata_path`; `env.provisioning.started` carries `classification` and `base_work_dir`; `env.provisioning.finished` carries `workspace_path`; and `checkpoint.saved` carries `checkpoint_id`, `kernel_checkpoint_id` and `checkpoint_dir`, each path relative or `null`. A `runtime_kernel.<operation>` event carries `operation`, `recorded_at`, `required`, `forwarded`, `ok`, `status`, `reason` and `error`, never the kernel's answer or its health. The other event types are built by the runtime from named fields, and their `payload` is sent as it was recorded. A live event's `payload` is an object, as a stored one is.

Not projected yet: `GET /api/runtime/readiness`, the operator diagnostics, reports the runtime root's `path`, the kernel's health and the kernel's last answer per operation; the artifact rows (`path`) and the checkpoint rows (`checkpoint_dir`, `manifest_path`, `patch_path`), the `details` of the task's `warnings`, and the `artifact` of an `artifact_ready` event carry host paths.

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
