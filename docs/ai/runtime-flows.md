# Runtime Flows

For the public operator-facing narrative, see [`../architecture/runtime.md`](../architecture/runtime.md). This document is the repository-oriented runtime flow reference for contributors and AI tooling.

This document describes the main runtime paths that matter when changing behavior.

Use [`repo-map.yaml`](repo-map.yaml) first if you need a compact path index for owners, tests, and related docs before reading the narrative flow description below. Use [`llm-compatibility.md`](llm-compatibility.md) for provider entrypoints and compatibility rules.

## 1. Message Or Command To Provider Response

1. Telegram updates enter through handlers registered in [`../../koda/__main__.py`](../../koda/__main__.py).
2. Command handlers in [`../../koda/handlers`](../../koda/handlers) or message handlers in [`../../koda/handlers/messages.py`](../../koda/handlers/messages.py) normalize input and call queue entrypoints.
3. [`../../koda/services/queue_manager.py`](../../koda/services/queue_manager.py) stores the request in a per-user queue and starts a worker when needed.
4. `_prepare_query_context` builds the effective execution context:
   - validates the working directory
   - checks cumulative budget
   - ensures the canonical agent session id exists before the first provider turn
   - resolves the active provider, provider-native session mapping, and provider-specific model
   - starts with `DEFAULT_SYSTEM_PROMPT`, whose agent-local compiled contract is injected from the control-plane runtime snapshot through `AGENT_COMPILED_PROMPT_TEXT`
   - appends optional user instructions
   - appends voice-specific prompt rules when voice mode is active
   - fetches memory recall context asynchronously
   - extracts typed artifact bundles from Telegram files and user-uploaded media
   - proactively builds Jira issue dossiers when the query mentions an issue key or Jira browse URL
   - appends runtime agent tool instructions
   - appends runtime skills-awareness prompt
   - downgrades the task to read-only planning mode when critical artifacts remain partial or unresolved
5. Execution is routed through [`../../koda/services/llm_runner.py`](../../koda/services/llm_runner.py), which dispatches to [`../../koda/services/claude_runner.py`](../../koda/services/claude_runner.py) or [`../../koda/services/codex_runner.py`](../../koda/services/codex_runner.py), usually with streaming enabled.
6. If the active provider cannot start or continue the task, the queue manager can temporarily fall back to the other provider and bootstrap it from the canonical transcript.
7. The response is post-processed and sent back through Telegram, including bookmark buttons, artifact delivery, code-block extraction, provider/model status, and optional TTS.
8. Query metadata, canonical sessions, provider-native session mappings, and task metadata are written through the typed primary stores, and memory extraction runs after successful completion.

## 2. Runtime Agent Tool Loop

The agent has a second execution loop beyond native provider CLI tools.

1. The active provider emits `<agent_cmd>` tags inside the textual response.
2. [`../../koda/services/tool_dispatcher.py`](../../koda/services/tool_dispatcher.py) parses those tags into tool calls.
3. Write operations are blocked in supervised mode and surfaced back as a confirmation requirement.
4. Tool handlers run with timeouts and feature-gate checks.
5. Results are converted into `<tool_result>` tags.
6. The queue manager resumes the active provider with those results, optionally downgrading to a smaller provider-local model for simple resumes.
7. If the provider resume path fails and no native resume state exists for the fallback provider, the runtime bootstraps a new native session with the canonical transcript plus the in-flight tool-loop context.
8. The loop repeats until there are no more agent commands, a cycle is detected, or the iteration limit is reached.

## 3. Text, Image, Document, And Audio Intake

### Text

- [`../../koda/handlers/messages.py`](../../koda/handlers/messages.py) reads plain text and reply context, then enqueues the resulting query.
- Link-only messages can be intercepted for link analysis before they ever reach the selected provider.

### Images And Documents

- Images are downloaded, tracked for cleanup, and wrapped into a query built by image utilities.
- Supported documents are downloaded and wrapped into a query built by document utilities.
- Both paths are converted into typed artifact bundles before entering the queue.
- The artifact layer extracts structured text, OCR, spreadsheet structure, and media evidence; only true visual assets are passed as provider image attachments.

### Audio

- Voice notes and audio files are downloaded and transcribed.
- The transcription is converted into a text prompt and then follows the normal queue path.
- Audio download artifacts are cleaned up after transcription.

## 3.1. Jira Deep Context Dossier

- [`../../koda/services/jira_issue_context.py`](../../koda/services/jira_issue_context.py) resolves issue metadata, comments, ADF media refs, attachments, remote links, and supported URLs into one dossier.
- [`../../koda/services/artifact_ingestion.py`](../../koda/services/artifact_ingestion.py) performs type-specific extraction for PDFs, DOCX, spreadsheets, text, images, audio, and videos, with OCR fallback when useful.
- Public video links referenced in Jira content are treated proactively as video sources when the URL is safely reachable, either through direct media resolution or a bounded `yt-dlp` download path for supported public pages.
- The resulting dossier is rendered into `<artifact_context>` blocks inside the system prompt, ranked against the live query, and also recorded in the execution trace.
- If any critical artifact remains `partial`, `unresolved`, or `unsupported`, the queue manager keeps the task in read-only mode even if the original request was operational.

## 4. Session, Cost, And Task Tracking

- `context.user_data["session_id"]` now stores the canonical agent session id instead of a provider-native session id.
- Provider-native session or thread ids are mapped through the Postgres-first history/runtime stores.
- Query history, provider usage and cost data, user cost totals, and task rows are persisted through typed state stores instead of repo-local SQLite files.
- In-memory task tracking in [`../../koda/services/queue_manager.py`](../../koda/services/queue_manager.py) supports status reporting, cancellation, and concurrency control.

## 5. Memory Lifecycle

1. Before the main provider runs, the queue manager asks the memory manager for recall context.
2. Recall is time-bounded and non-fatal.
3. After the provider returns, the memory manager extracts candidate memories from the query and response, using the configured memory extraction provider and model.
4. New memories are persisted and recall caches are invalidated.
5. Scheduled digest and maintenance jobs operate separately from the main interaction path.

## 6. Scheduler And Automation Flow

- The scheduler domain is split across:
  - [`../../koda/services/scheduled_jobs.py`](../../koda/services/scheduled_jobs.py) for job definitions, persistence helpers, and control APIs
  - [`../../koda/services/scheduled_job_dispatcher.py`](../../koda/services/scheduled_job_dispatcher.py) for due-run materialization, leasing, catch-up, and dispatcher wake/start/stop
  - [`../../koda/services/scheduled_job_runtime.py`](../../koda/services/scheduled_job_runtime.py) for execution dispatch, completion/failure handling, retries, verification, and notifications
- These modules are backed by the shared primary scheduler store and its Postgres-backed tables.
- New jobs are created in validation-first mode. A manual test or dry-run run is queued before the job can be activated.
- Due runs are materialized from the persistent job definition, leased by the dispatcher, and then either:
  - enqueue an `agent_query` occurrence back into [`../../koda/services/queue_manager.py`](../../koda/services/queue_manager.py)
  - execute a `reminder`
  - or execute a read-only `shell_command` scheduled job
- Scheduled agent execution routes back through the same agent runtime, which means provider fallback, canonical sessions, memory, knowledge retrieval, approvals, and queue behavior still apply.
- Completion updates the scheduled run ledger with task ids, provider/model, verification result, retries, notifications, and fallback metadata.
- Legacy cron commands remain available through [`../../koda/services/cron_store.py`](../../koda/services/cron_store.py), but they are now compatibility wrappers over the unified scheduler.
- Digest and maintenance schedulers in [`../../koda/memory`](../../koda/memory) follow the same general pattern: schedule outside the main request path, execute without blocking normal message handling.

## 7. Failure Handling Principles

- Provider CLI timeouts are surfaced as user-visible failures rather than hanging indefinitely.
- Retry logic and fallback only apply to recognized transient failures.
- Memory failures degrade gracefully.
- Tool-loop errors are returned to the active provider as tool results whenever possible.
- Security and approval blocks are treated as expected outcomes, not exceptional crashes.
- Circuit breakers and fallback warnings are part of normal observability, not hidden implementation details.
