# Architecture Audit

Phase Zero output defined in [MISSION.md](MISSION.md) §4 and §5. First cut, to be
refined into ADRs and the backlog in `MASTER_PLAN.md`.

| Field | Value |
|---|---|
| Date | 2026-11-14 |
| Baseline | `7b848cf` on `claude/dreamy-cerf-mhvbwn` |
| Inputs | 13 specialist reviews (771 file reviews, with overlap), the debt register they produced, and spot measurements at HEAD |
| Companions | [EXECUTION_STATUS.md](EXECUTION_STATUS.md), [QUALITY_BASELINE.md](QUALITY_BASELINE.md), [VALIDATION_REPORT.md](VALIDATION_REPORT.md); `SYSTEM_INVENTORY.md`, `FEATURE_MATRIX.md` and `TECHNICAL_DEBT.md` are pending |

## Contents

1. [Scope and evidence labels](#1-scope-and-evidence-labels)
2. [Summary](#2-summary)
3. [Current architecture](#3-current-architecture)
4. [Strengths worth preserving](#4-strengths-worth-preserving)
5. [Structural problems](#5-structural-problems)
6. [Defects with structural root causes](#6-defects-with-structural-root-causes)
7. [Target architecture (first cut)](#7-target-architecture-first-cut)
8. [Decisions per component](#8-decisions-per-component)
9. [Migration sequence](#9-migration-sequence)
10. [Risks](#10-risks)
11. [Decisions needed](#11-decisions-needed)

---

## 1. Scope and evidence labels

Every finding carries one of these labels:

| Label | Meaning |
|---|---|
| **V** | Verified by execution during discovery: a probe, simulation, rendered config or targeted test run by a specialist or the orchestrator |
| **C** | Code-read: traced through source but not executed |
| **U** | Unverified: inferred, or depends on deployment facts not available in this environment |
| **M** | Measured at HEAD by the architect (`wc -l`, directory listing) |
| **F** | Fixed at HEAD; the commit is named |

Limits of this audit:

- No live provider calls, no Docker daemon and no browser runs. Mobile and keyboard findings for the web UI are code-read.
- Of the Rust sidecars, only `security-service` (auto-started by `tests/conftest.py`) and `bot-gateway` (one integration test) were exercised for real from Python. `memory`, `retrieval`, `artifact` and `runtime-kernel` were checked only against fakes.
- During specialist runs the Postgres-backed squad, bus and router tests were skipped. The Postgres suite itself became runnable at `30a7fe5`, but the new CI job has not run yet.
- The reviews give different counts for the same things, depending on how they counted:
  - Env vars: 369 to 387 read in `koda/config.py`, about 606 across `koda/`. Documented: 68 in `docs/config/reference.md`; `.env.example` is counted as 39 by one review and 191 by another.
  - Control-plane routes: 302 by the control-plane and product reviews, 299 by the web review.

  Where this document uses a figure it states the source. Re-measure before using any count as a gate.

## 2. Summary

- **Shape.** About 175k lines of Python (**M**) under a Next.js console of about 179k lines of TS/TSX/CSS (**M**, of which about 32k is i18n resources), plus a 12-crate Rust workspace of about 19.8k lines (**M**). The system runs as a Python supervisor (control plane) and one Python worker per agent, which the Rust runtime-kernel spawns. The default stack is 10 containers: `app`, `web`, five Rust gRPC services (runtime-kernel plus 4 sidecars), Postgres, SeaweedFS and its init job; 2 more Rust sidecars are opt-in profiles.
- **Distributed monolith.** The sidecars all read and write one Python-owned Postgres schema through hand-written SQL. They have no RPC authentication and ship in lockstep. Only the runtime-kernel, which owns child processes, earns its process boundary (**C**).
- **Concentration.** Five files hold about 41k lines of core logic (**M**): `control_plane/manager.py` (15,061), `services/queue_manager.py` (9,438), `control_plane/api.py` (5,850), `services/tool_dispatcher.py` (5,518) and `knowledge/v2/postgres_backend.py` (5,296). The last of these is the schema owner for the whole app: 130 tables in 50 inline migrations.
- **Fragmentation.** Most cross-cutting concerns have 2 to 9 implementations. Examples: 9 enqueue variants, 5 tool catalogs, 2 policy evaluators that disagree (**V**), 8 policy stores, up to 4 shell-blocklist checks per command and 7 MCP server-start sites.
- **Process-boundary mismatches.** Some state is assumed to be shared across supervisor, worker and kernel but actually lives in one process's memory. Examples: dashboard approvals, the recall cache and the in-memory squad bus.
- **Blocking bridge.** About 226 `run_coro_sync` call sites run synchronous Postgres calls (up to 30 s) and synchronous gRPC calls on async event loops (**C**).
- **Tests hide broken paths.** 212 of 324 test files mock (2,145 `patch(` calls). `_execute_single_task` is always patched out, and an autouse fixture grants execution approval globally. Many verified defects (section 6) sit on paths the suite never exercises.
- **Target.** A modular monolith: Python (control-plane process plus per-agent workers), Node (web/BFF) and a single Rust process (runtime-kernel). This takes the default containers from 10 to 6 (5 services plus the S3 init job). God modules are split along seams that already exist, with one implementation per concern. This is an incremental strangler migration, not a rewrite.

## 3. Current architecture

### 3.1 Process and service topology

```
Browser
  |  same-origin HTTPS, sealed session cookie
  v
web  (Next.js 16 + server.mjs WS relay)            :3000, published on all interfaces (V)
  |  /api/control-plane/*  Bearer operator token
  |  /api/runtime/agents/* per-agent HMAC token (300 s) from /agents/{id}/runtime-access
  v                                         \
app  (Python supervisor)                     \--> agent worker runtime API (/api/runtime/*, /ws/runtime)
  - control-plane aiohttp API (302 routes)  :8090, published on all interfaces (V)
  - reconcile loop (5 s) -> publish -> runtime snapshot
  |  gRPC EnsureAgentWorkers
  v
runtime-kernel  (Rust binary inside a full copy of the Python app image)
  - spawns one Python agent worker per agent as a child process
      agent worker: PTB Telegram bot, queue_manager, tools, MCP stdio servers,
                    scheduler, health/metrics/runtime API
         |  gRPC (UDS or TCP, no auth): security, memory, retrieval, artifact,
         |  runtime-kernel, [policy-engine], [bot-gateway]
         v
Rust sidecars ---------------> Postgres 16 + pgvector (one schema "knowledge_v2", ~130 tables)
Python stores (run_coro_sync) -^   SeaweedFS S3 (artifact blobs, knowledge payload copies)
Telegram Bot API <--- long polling from each worker (PTB)
```

| Service | Lang | Responsibility | Notes |
|---|---|---|---|
| `app` | Python | Supervisor: control-plane API, reconcile loop, sidecar health probes (`channel_ready` only) | Holds the Fernet master key file; delegates worker spawning to the kernel |
| `web` | Node | Operator console, BFF route handlers, WS relay for terminal/browser attach | Custom HTTP/1.1 server; no serverless deploy |
| `runtime-kernel` | Rust | Agent-worker supervision, task environments, terminals, browser/VNC, checkpoints | In-memory state not reconciled with Python `runtime_*` tables (**C**) |
| agent worker (×N) | Python | Channel intake, execution, tools, memory, scheduling, runtime API | Not a compose service; children of the kernel; one agent per process |
| `security` | Rust | Shell/path validation, env sanitisation, redaction | Hard availability dependency (**C**) |
| `memory` | Rust | Memory recall, curation projections, `napkin_log` writes | Second writer to a Python-owned table |
| `retrieval` | Rust | Knowledge retrieval (lexical, dense, graph) | Reads tables that nothing writes in primary mode (**C**) |
| `artifact` | Rust | Artifact blobs (S3 or Postgres) | Artifact ingestion hard-fails without it (**C**) |
| `policy-engine` | Rust | Quotas (opt-in profile) | No operator configuration surface (**C**) |
| `bot-gateway` | Rust | Telegram long-poll gateway (opt-in profile) | Acks failed updates despite at-least-once claim (**C**) |
| `postgres` | pg16 + pgvector | Only durable store | |
| `seaweedfs`, `seaweedfs-init` | S3 | Object store and bucket bootstrap | |

The overlays (`dev`, `prod`, `cluster`, `observability`) are untested in CI. Known problems:

- `prod`: appends ports instead of replacing them (**V**, orchestrator).
- `cluster`: gives every replica the same supervisor ID (**C**).
- `observability`: scrapes a `/metrics` endpoint that the control plane does not serve, and worker metrics bind to loopback inside the kernel container (**C**).

There are two separate distribution paths:

- **Source:** `docker-compose.yml` plus its overlays.
- **Release:** the npm CLI with a hand-maintained `docker-compose.release.yml`.

They have diverged on tokens, limits, volumes and network membership, and only string tests check them (**C**).

### 3.2 Code size and concentration (M)

| Python package | Lines | | Largest files | Lines |
|---|---:|---|---|---:|
| `koda/services` | 64,656 | | `control_plane/manager.py` | 15,061 |
| `koda/control_plane` | 32,410 | | `services/queue_manager.py` | 9,438 |
| `koda/knowledge` | 12,436 | | `control_plane/api.py` | 5,850 |
| `koda/squads` | 9,875 | | `services/tool_dispatcher.py` | 5,518 |
| `koda/internal_rpc` | 8,308 | | `knowledge/v2/postgres_backend.py` | 5,296 |
| `koda/state` | 8,250 | | `services/runtime/controller.py` | 4,035 |
| `koda/handlers` | 7,191 | | `rust/koda-runtime-kernel/src/server.rs` | 4,212 (specialist) |
| `koda/utils` | 6,530 | | `rust/koda-memory-engine/src/main.rs` | 3,489 |
| `koda/memory` | 5,892 | | `rust/koda-retrieval-engine/src/main.rs` | 3,050 |
| `koda/channels` | 3,212 | | `apps/web/src/app/globals.css` | ~10.5k (specialist) |

Inside `queue_manager.py`, three functions are each about 1k lines: `_execute_single_task` (1,161), `_prepare_query_context` (948) and `_run_agent_loop` (938). Ten web components or hooks are over 1,000 lines, led by `use-system-settings.tsx` (2,847) and `agent-catalog.tsx` (2,769).

### 3.3 Request and data flow

**Telegram message (primary path), C:**

1. PTB processes updates one at a time by default. A group `-1` handler records the offset, then the command handler runs `auth_check` and `enqueue()`. Auth is checked per handler; an AST scan found no unguarded public handler (**V**), but there is no central filter.
2. `enqueue` applies the policy gate. `create_task` writes synchronously to Postgres through `run_coro_sync`. The item then goes onto a per-user `asyncio.Queue`, a `runtime_queue` row is persisted, and `_ensure_queue_worker` is called.
3. `_process_queue` is one sequential worker per user and calls `_execute_single_task`:
   1. Acquire the global and class semaphores; optionally provision a runtime environment.
   2. Acquire the task lease and start renewal.
   3. `_prepare_query_context` runs under the per-user lock: budget, prompt segments, memory, knowledge, cache, artifacts, skills, squad context, prompt budget and governance.
   4. Attempt loop: cache short-circuit, then `_run_with_provider_fallback`. Each provider is tried streaming first (`run_llm_streaming`), then non-streaming (`run_llm`). The agent loop executes `<agent_cmd>` tools and resumes through the same fallback.
   5. Grounding gate. It can force `needs_review` and replace the response.
   6. `_prepare_delivery_outcome` (artifact scan), then `_post_process` under the lock (sessions, cost, history, memory extraction, squad fan-out), then `_send_response`, then `update_task_with_lease(completed)`.

**Other intake paths.** Dashboard chat, scheduled runs, continuations, link analysis, squad turns, runtime retries and child runs each have their own enqueue variant, nine in total (`queue_manager.py:2047-2338, 9153-9438`). Each repeats create, put, track, persist, observe and spawn, with different shutdown, capacity and policy checks. The variants pass options as raw `dict`s with underscore flags (`_scheduled_run`, `_dashboard_chat`, `_child_run`). The large carrier dataclasses are `QueueItem` (37 fields), `QueryContext` (66 fields) and `RunResult`.

**Scheduled jobs.** The scheduled-job dispatcher (in the worker) calls `enqueue_scheduled_run`, which leads to `handle_run_success` or `handle_run_failure`, and sends notifications over Telegram. `scheduled_jobs.py` monkey-patches the dispatcher's module global at import time and re-exports about 20 private functions (**C**).

**Squads.** A message arrives either from a Telegram forum (`squad_handlers.route_squad_supergroup_message`) or from a web `POST /squads/threads/{id}/messages`. It is stored as a `squad_messages` row, and then one of two copies of the routing pipeline runs: semantic rank, mentions, triage, then the LLM coordinator. `dispatch_squad_turn` tries three transports in order: the local queue (which can run another agent in-process through `executing_agent_id`), then runtime HTTP, then the message bus. Post-turn squad logic (obligations, task advance, synthesis, delegation) runs inside `queue_manager._post_process`.

**Providers.** There are 4 native adapters: the Claude, Codex and Gemini CLIs, and Ollama over urllib. Ten OpenAI-compatible profiles run behind one aiohttp adapter. Adapters return dicts with keys such as `_error_kind` and `_retryable`, which `llm_runner` normalises. Retries happen in four layers: the adapter (Claude only, through tenacity), stream-to-fallback, the provider chain, and the task level.

**Tools and policy.**

1. The provider emits `<agent_cmd>` XML or native tool calls.
2. `_run_agent_loop` evaluates `evaluate_execution_policy`: secure default, rules, integration grants and overlays.
3. If the decision needs confirmation, the user is asked through a Telegram keyboard or the dashboard broker. The resulting grant is bound to a resource/params fingerprint.
4. `execute_tool` re-checks the rate limit, the supervised contextvar, dry-run and the timeout, writes the `cp_integration_grant_audit` row, and calls the handler.
5. The result is formatted and the provider resumes.

Provider CLIs run with their native permissions bypassed: Claude with `bypassPermissions`, Codex with `danger-full-access`, Gemini with `yolo`. Koda's gates therefore govern only `<agent_cmd>` calls (**C**).

**Config publish.**

1. The operator edits the agent in the web UI, which calls the control plane.
2. `cp_agent_config_versions` stores the snapshot, with secret ciphertext embedded.
3. The reconcile loop calls `build_runtime_snapshot`, then the kernel's `EnsureAgentWorkers`.
4. The worker starts with the published env.

Because the snapshot embeds ciphertext, secret changes require a republish (**C**).

**Web BFF.**

- The browser calls only same-origin routes.
- `proxy.ts`:
  - rate-limits;
  - blocks cross-site mutations;
  - checks that a session cookie exists;
  - routes pages to `/login` or `/setup`.
- `/api/control-plane/[...path]`:
  - unseals the operator token into a Bearer header;
  - validates request bodies with zod;
  - zeroes secret `value` fields in responses.

  When the control plane is down it returns synthetic HTTP 200 payloads.
- `/api/runtime/*` routes get a per-agent base URL and token, then call the worker runtime API directly.
- `/api/channels/*` handles decrypted channel secrets in the web tier.
- The TypeScript types for these contracts are written by hand to mirror the Python routes. Three drift mismatches were found: mentions, block submit and `commands/list`.

### 3.4 Persistence

| Aspect | Current state |
|---|---|
| Store | One Postgres (pgvector pg16) holds all state in schema `knowledge_v2`; S3 (SeaweedFS) holds blobs. `STATE_BACKEND` is effectively fixed to `postgres`; `history_store.py` keeps 29 dead SQLite branches (**C**) |
| Schema owner | `koda/knowledge/v2/postgres_backend.py`: 130 tables, 50 inline forward-only migrations as Python strings, applied both at boot and by `python -m koda migrate`. There is no down path, so `koda update` rollback cannot undo them (**C**) |
| Tables outside the registry | Approval tables (`state/pending_approvals.py:63`, `state/approval_grants.py:93`). The artifact engine table runs DDL with an exclusive lock on every request (**C**). Rust tests hand-copy knowledge DDL |
| Integrity | 7 foreign keys across 130 tables. 95 TEXT timestamp columns vs 73 TIMESTAMPTZ. INTEGER booleans and INTEGER Telegram IDs. `agent_id` is uppercase in knowledge and control-plane rows, lowercase in memory rows (**C**) |
| Access path | Synchronous facades in `koda/state/*` (~226 `run_coro_sync` sites) over one asyncpg pool. The squad stack opens 10 more pools. Each Rust service opens its own pool to the same DSN |
| Cross-language contract | None beyond hand-written SQL. Rust reads and writes Python-owned tables (`napkin_log`, `query_history`, `audit_events`, `cp_telegram_offsets`), so a Python migration can break Rust at runtime (**C**) |
| Process-local state | Per-user queues, locks and the task registry; pending approvals; MCP dispatcher dicts; recall cache; in-memory bus; kernel environment state |
| Secrets | Fernet master key file on a volume (no backup tooling) encrypts `cp_secret_values`. The same key is reused as an HMAC key, and `rotate_master_key` has no production caller (**C**) |
| Duplicated persistence | Runtime events go to both `runtime_events` and a per-task `events.ndjson`. Approvals keep JSON fallbacks in `STATE_ROOT_DIR` |
| Retention | The daily purge targets tables that do not exist (**C**). Memory retention uses soft deactivation only |

### 3.5 Python to Rust boundaries

| Crate | Lines (M) | Called from | Postgres | Assessment |
|---|---:|---|---|---|
| `koda-runtime-kernel` | 7,176 | Supervisor (`runtime_kernel_link.py`) and worker (`internal_rpc/runtime_kernel.py`): two clients, two channels, two breakers | None; state in memory | Real process supervisor (child processes, PTYs). Justified |
| `koda-security-service` + `-core` | 190 + 533 | Worker, through synchronous gRPC on every LLM subprocess env build, shell command and redaction. The kernel also links `-core` as a library | None | A network hop for pure functions. When it is down, shell is blocked and redaction raises |
| `koda-memory-engine` | 3,489 | `MemoryStore` (recall, dedupe, curation) | Direct; second writer to `napkin_log` | About 90% dashboard projections. The Deduplicate RPC is a no-op that write paths still require |
| `koda-retrieval-engine` | 3,050 | `KnowledgeManager.resolve` | Direct; reads `knowledge_v2` tables | Well-tested read side over tables that no producer writes in primary mode |
| `koda-artifact-engine` | 1,561 | Artifact ingestion, runtime controller | Direct, plus S3 | Duplicates the Python S3 access; owns a table outside the registry |
| `koda-policy-engine` | 1,247 | Opt-in; no entry point configures it | Raw `tokio_postgres` client, bypassing the shared pool | No consumer |
| `koda-bot-gateway` | 1,583 | Opt-in Telegram gateway | `cp_telegram_offsets` | Duplicates PTB polling |
| `koda-command-guard` | 115 | PyO3 wheel, never installed in any image | None | Production uses the Python fallback |
| `koda-postgres`, `-proto`, `-observability` | 753, 66, 20 | Shared libraries | | Shrink as services consolidate |

Cross-cutting: there is no RPC authentication; `x-agent-id` metadata is advisory and agent scope is whatever the caller sends. TLS is partial. `INTERNAL_RPC_MODE` is hard-coded to `rust`, and `select_engine_backend` ignores its argument. Each client has a Protocol with a single implementation. `_filter_request_kwargs` silently drops unknown proto fields. `buf` uses deprecated v1beta1 config and is not enforced in CI (**C**).

## 4. Strengths worth preserving

| Strength | Where | Evidence |
|---|---|---|
| Fail-closed execution policy: shell, file, git, MCP and workdir tools are denied until granted. Grants are fingerprinted, and the model's `allow_private` is overridden by the grant decision | `services/execution_policy.py`, `agent_contract.py` | **V** (runtime evaluation) |
| Control-plane-first publishing: versioned config snapshots, server-side publish checks, worker env derived from the snapshot | `control_plane/manager.py`, `cp_agent_config_versions` | **C** |
| Single-owner operator auth: Argon2id, sessions, PATs, recovery codes, bootstrap code, one auth middleware. Placeholder-secret gap closed | `control_plane/operator_auth.py`, `api.py:329-368` | **V** (88 tests); **F** `3f895ee` |
| Durable tasks with startup recovery; per-user FIFO ordering is simple and predictable | `queue_manager.py`, `history_store.py` | **V** (happy-path suites, 475 tests) |
| OpenAI-compatible providers consolidated behind one adapter with profile builders | `openai_compatible_runner.py` `_PROFILE_BUILDERS` | **C** |
| Squad core: Postgres threads and tasks with CAS claims; bounded reply obligations (depth 6, 20 open, 2 follow-ups); coordinator fan-out cap of 5; prompt isolation through `SquadAccessService` | `koda/squads/*` | **C** (Postgres paths not executed) |
| Child runs fenced from memory recall and writes by default | `koda/memory` | **C** |
| One durable database. No redundant state engines, only redundant access paths | Postgres + pgvector | **C** |
| Runtime-kernel as the one process that owns OS resources | `rust/koda-runtime-kernel` | **C** |
| Accurate API inventory: the OpenAPI path list matches the code exactly | `docs/openapi/control-plane.json` | **V** (302/302) |
| BFF boundary: the browser talks only to same-origin routes, request bodies are validated with zod, and secret values are zeroed in proxy responses | `apps/web/src/app/api/control-plane/[...path]` | **C** |
| Secrets encrypted at rest, used consistently | `control_plane/crypto.py` | **C** |
| `uv.lock` drives images and CI. CI is broad: ruff, mypy, a pytest matrix, a Postgres job, web lint/test/build, Rust fmt/clippy/test and docker-smoke | `.github/workflows/pr-quality.yml` | **C** |
| Web foundations: Radix, Tailwind v4, a single icon library, an i18n key-parity contract test and a glass-blur contract test | `apps/web` | **V** (vitest suites green) |
| Healthy feature slices worth using as reference patterns: evaluations, account settings | `apps/web` features, backend tests | **C** |

## 5. Structural problems

### 5.1 Concentration (god modules)

| Module | Mixed responsibilities | Natural seams |
|---|---|---|
| `services/queue_manager.py` | Intake, persistence, leases, context assembly, provider orchestration, agent loop, delivery, voice, artifacts, about 1k lines of squad logic, DLQ; global state shared with handlers and the runtime controller | intake, worker/lease, context builder, provider executor, agent loop, delivery, squad hook, scheduled/DLQ adapters |
| `control_plane/manager.py` | One class with 241 methods: agents, providers, model downloads, MCP, OAuth, evals, dashboards, workspaces, secrets. `ensure_seeded` runs legacy repairs on every `list_agents`/`get_agent`; `get_agent` runs about 20 queries | agents/publish, secrets, providers/auth, integrations, policies, quality, dashboard read models, workspaces/squads |
| `control_plane/api.py` | 302 thin handlers in one file; 32 handlers re-run auth after the middleware | One router per domain |
| `services/tool_dispatcher.py` | Gate logic alongside handlers for jobs, web, browser, files, shell, git, plugins, workflows, webhooks and about 1,600 lines of squad tools | `tools/policy`, `tools/handlers/<family>` |
| `knowledge/v2/postgres_backend.py` | Schema and migrations for the whole app, plus pool management, plus knowledge persistence, under a misleading package name | `state/migrations`, `state/db`, per-domain repositories |
| `services/runtime/controller.py` | Workspace files, git diff/search, terminals, browser/VNC, checkpoints, kernel cutover, sweeps, metrics. Opt-in and off by default | Only if the feature stays in scope (D-8) |
| `koda/config.py` | 381 env keys read into module constants at import time, causing import-order coupling; tests patch every module that copied a constant (`tests/postgres_fixtures.py:90-146`) | Typed settings object |

### 5.2 Fragmentation (multiple implementations of one concern)

| Concern | Copies | Locations | Consequence |
|---|---:|---|---|
| Task enqueue | 9 | `queue_manager.py` variants | Inconsistent shutdown, capacity and policy checks |
| Retry and error classification | 4 layers | `claude_runner.py:287`, `llm_runner.py:85-114`, `queue_manager.py` (several) | Side-effecting tools re-run; PT-BR/EN keyword heuristics turn errors into successes |
| Provider metadata | ~7 modules | `config.py`, `agent_contract.py`, `provider_models.py`, `provider_auth.py`, `llm_runner.py`, `openai_compatible_runner.py`, `provider_runtime` | Adding a provider touches many files; `supports_native_resume` is defined twice |
| Tool catalog | 5 | `_WRITE_TOOLS`/`_READ_TOOLS`/`_TOOL_HANDLERS`, `tool_prompt`, `CORE_TOOL_CATALOG`, `tool_registry` | Measured drift: 26 handlers missing from the catalog; `request_skill` is read in one place and write in another |
| Execution policy evaluator | 2 | `services/execution_policy.py`, `control_plane/execution_policy.py` | Different decisions for the same validated policy (**V**) |
| Policy stores | 8 | Tool, model, autonomy, execution, resource-access, MCP-tool, connection-tool and capability policies | Three are already labelled legacy; the legacy path is still the default |
| Approval gating | 5 gates | Policy, contextvar, supervised check, dry-run, `_approved` flag | Gates contradict each other; shell/git/supervised paths broken (**C**) |
| Shell blocklist | 3–4 | `config.py:626-683`, `cli_runner.py`, `shell_safety.py`, `tool_dispatcher.py`, Rust `validate_shell_command`, kernel `commands.rs:120` | Up to four checks per command; still easy to bypass |
| Safe-path resolution | 4 | `utils/files.safe_resolve`, `_validate_file_path`, `validate_work_dir`, `validate_runtime_file_path` | `/cat` can print `.env` while `file_read` cannot |
| Redaction | 3 | `audit.py`, `runtime/redaction.py` (Rust), `evals.py` | Different coverage per path |
| HTTP clients | 2 stacks | aiohttp; urllib (Ollama, provider auth, MCP HTTP, OAuth) | Different SSRF and redirect semantics; blocking calls |
| MCP server start | 7 sites | `mcp_bootstrap`, `mcp_bridge`, `mcp_capability_service`, 4 in `manager.py` | None applies the isolation settings |
| MCP catalog, MCP env decrypt | 2, 3 | `control_plane/mcp_catalog.py` (used only by a test); three decrypt helpers | |
| Squad inbound routing | 2 | `handlers/squad_handlers.py:447-725`, `control_plane/api.py:~1260-1560` | Already diverging on status gating |
| Squad dispatch transport | 3 | Local queue, runtime HTTP, bus | Unclear idempotency; metadata lost on the local path |
| LISTEN/NOTIFY listener | 2 | `agents/listen_notify.py` (reconnects), `squads/event_hub.py` (does not) | |
| Postgres pools | 1 + 10 + one per Rust service | `koda/state`, `koda/squads/*`, Rust services | Connection fan-out |
| `napkin_log` writers, recall scoring | 2, 2 | Python `napkin.py` and Rust curation; Rust and Python scorers run in series | Neither is tested on real data |
| Runtime-kernel clients | 2 | `internal_rpc/runtime_kernel.py`, `control_plane/runtime_kernel_link.py` | Two config aliases for one target |
| Settings modules | 4 | `config.py`, `control_plane/settings.py`, `cache_config.py`, `confidence_config.py` | Violates the CLAUDE.md centralisation rule |
| Background loop mechanisms | 3 | `lifecycle_supervisor`, the scheduler's own task, 5 raw controller tasks | Only one mechanism is visible in health |
| Semantic cache | 3 strategies | Exact hash, chunked embedding scan, FAISS | FAISS and sentence-transformers not declared in `pyproject` |
| Extension manifests | 2 | `plugin.yaml`, `koda-skill.yaml` | |
| Dashboard aggregation | 2 | `control_plane/dashboard_service.py`; unused `apps/web/src/lib/runtime-dashboard.ts` plus 8–10 routes | Different semantics; the Node copy has no caller |
| Web fetch/error helpers | 7+ / 3 parsers | `http-client.ts`, `control-plane-dashboard.ts`, several components | Error and abort handling differ per screen |
| Web SSE reconnect loops | 4 | `use-runtime-overview`, `use-runtime-task`, `use-session-stream`, `use-squad-thread-events` | |
| Web nav metadata, buttons, error states | 3, 2, 2 | `sidebar-nav.tsx`, `route-meta.ts`, command registry; `Button` vs `ActionButton` | Already disagree |
| Web caching policies | 3 | `query/client.ts`, `query/options.ts`, `pagination.ts` | |
| Compose and images | 2 compose paths, 6 near-identical Rust Dockerfiles, 2 ~6 GB Python images | Repo root, `packages/cli/release/bundle` | Changes made twice; slow builds |
| CI and dependency manifests | `release.yml` re-implements PR and security jobs; `requirements.txt` mirrors `pyproject`; dev deps declared twice | `.github/workflows`, `pyproject.toml` | |

### 5.3 Over-engineering (complexity without a current consumer)

| Item | Evidence |
|---|---|
| 5–7 gRPC sidecars for one schema | No independent deploy, no auth, lockstep releases; only the kernel owns OS resources (**C**) |
| Multi-worker lease and janitor for a single-process in-memory queue | Lease loss is not acted on; janitor requeues are not consumed (**C**; deployment cardinality open, D-1) |
| `AgentTurn` (672 lines) and `RunGraph` (~1.7k lines plus a second store and two routes) | Only consumers are audit payloads and a graph rebuilt from the already-persisted trace (**C**) |
| Report-only context governance on main runs | Computes allow/deny after compilation and changes nothing (**C**) |
| Cluster mode | Leader election and placement for a single-owner product; unauthenticated `/cluster/*`; replicas share an ID (**C**) |
| Policy-engine, bot-gateway, command-guard | No configuration surface, duplicate of a live path, never shipped (**C**) |
| Memory dedupe RPC, namespaces/sensitivity, embedding queue/repair loop | No-op, never set, never produces embeddings (**C**) |
| Knowledge storage-mode layer | Five wrappers; `local_write_enabled()` always returns False; fire-and-forget hides write failures (**C**) |
| Single-implementation Protocols and backend selection in `internal_rpc` | Mode is hard-coded (**C**) |
| Improvement-proposal approve/validate/apply/rollback | `apply` writes a ledger row only (**C**) |
| Workflow engine | In-memory and sequential, with no persistence, UI or run-graph link (**C**) |
| Observability overlay, tracing scaffold | One span in the codebase; OTel SDK not in `uv.lock`; metrics unreachable (**C**) |
| No-op fallbacks for hard dependencies | `metrics.py`, `resilience.py` (**C**) |
| Web: generative-UI blocks (~1.8k lines), product tour (~2.8k), layered loading-state hooks, synthetic outage payloads (~230 lines), i18n layer (~32k lines, three translation paths) | No backend producer, an unreachable mode, duplicated `keepPreviousData`, a hidden outage, 1,116 load-time mutations (**C**) |
| Security scanning | Three SCA layers per ecosystem plus a custom dependency-review script (**C**) |
| Test tooling | Live-gate "smoke" that checks env vars only; 11 of 16 pytest markers unused; empty `tests/e2e` and `tests/eval` (**C**) |

### 5.4 Coupling hot spots

- `queue_manager` lazily imports nearly every subsystem: memory, knowledge, squads, runtime controller, tool dispatcher, audit, policy engine, artifacts and TTS. There is no hook interface.
- The runtime controller calls back into `queue_manager` for cancel and retry, so the dependency runs in both directions. Module-global queues, locks, the task registry and `active_processes` are shared with the handlers.
- Squads are spread across `queue_manager` (about 1k lines), `tool_dispatcher` (32 handlers), `control_plane/api.py` (a routing copy and 20 routes) and `squad_handlers.py`. Squad stores reach into each other's private `_ensure_pool` and `_schema`.
- `scheduled_jobs` monkey-patches its dispatcher, and the two use lazy imports of each other. This indirection hid the scheduled-run snapshot bug.
- Memory imports knowledge config and policy; knowledge imports `memory.procedural`. Both depend on `KnowledgeV2PostgresBackend` as the app-wide store.
- Rust services are coupled to Python migrations only through SQL strings.
- `koda.config` constants are copied at import time, so test fixtures must patch every module that holds a copy.
- Web: the chat composer imports from `control-plane/system/integrations`, hooks import component modules, the "rooms" name covers two unrelated concepts, and the agent catalog is mirrored into a mutable module global.

### 5.5 Process-boundary mismatches

| Assumed shared | Actual | Effect |
|---|---|---|
| Pending approvals | Worker memory; the control-plane API runs in the supervisor | Dashboard approval routes cannot see worker approvals (**C**) |
| Memory recall cache | Per process | Control-plane curation cannot invalidate the worker cache (**C**) |
| Squad bus with the memory backend | Per process; one process per agent | Non-functional for multi-agent use (**C**) |
| Kernel environment state | Kernel memory, not reconciled with `runtime_*` tables | Divergence after a kernel restart (**U**) |
| Worker metrics | Bound to loopback inside the kernel container | Nothing outside can scrape them (**C**) |
| Control-plane public paths | Two lists, in the web and in the backend | Already drifted (web includes `onboarding/readiness`) (**C**) |

### 5.6 Sync-over-async

The synchronous facades over asyncpg (`run_coro_sync`, `future.result` with a 30 s timeout) and the synchronous gRPC clients (security, retrieval) run on the worker and control-plane event loops. Every control-plane handler blocks the loop on Postgres (**V**, control-plane review). Combined with PTB's sequential update processing and handlers that hold the per-user lock, this can stall the whole bot (**C**). `__main__.py:787-795` documents the blocking itself.

### 5.7 Enforcement model

- Provider-native tools bypass every Koda gate. The Rust kernel adds no OS sandbox. The shell denylist is easy to bypass. Effective containment is therefore whatever the container provides (**C**; product intent open, D-4).
- Per-server MCP isolation settings (profile, constraints, egress allowlist) are stored but never applied. Bubblewrap does not implement the egress allowlist. Docker mode leaves secret env files behind (**C**).
- Skill-package and plugin code is loaded in-process, gated only by a denylist scanner. `PLUGIN_SANDBOX_ENABLED` is never read (**C**).
- Personal tokens have no scopes. Any token can read plaintext secrets with `include_value=true` and register stdio MCP servers (**C**).
- The gRPC sidecars on the `backend` network are unauthenticated. That network includes `runtime-kernel`, where agent tool code runs (**C**).

### 5.8 Configuration surface

`koda/config.py` reads 369–387 env vars, and `koda/` as a whole reads about 606 (method-dependent; see section 1). Roughly 5 settings exist per provider across 15 providers. 43 other modules read env directly. Most keys are undocumented. Some are exposed to operators but have no effect, for example `MEMORY_SIMILARITY_DEDUP_THRESHOLD`, the Neo4j settings and the `PLUGIN_*` flags. This contradicts the "dashboard owns product config" story (**C**).

### 5.9 Dead and unwired code (C unless noted)

| Area | Items |
|---|---|
| Python | `startup_validator`, `warm_provider_capabilities`, `is_admin`/`ADMIN_USER_IDS`, legacy tuple queue items, per-user semaphore, `DBManager` and its SSH tunnels (started at boot, never called), 8 non-Telegram channel adapters plus `ChannelManager` (~1.9k lines, 0 tests), `scheduler.py` and `cron_store.py` shims, `RuntimeStore` passthrough, webhook/event_wait/snapshot tools, legacy `/agents/{id}/mcp/connections/*` and eval route families, ~530 lines of legacy import, SQLite branches, Neo4j config |
| Rust | `koda-command-guard`, `koda-policy-engine` (no configuration path), `koda-bot-gateway` (opt-in, duplicate) |
| Web | 71 source files (~12k lines) unreachable from any route (**V**, import-graph script), including `components/tasks/*`, `components/audit/*`, dashboard cards, `control-plane/shared/*`, `system/mcp/*`, `lib/sse.ts`, `useSSE`, `useAsyncResource`, `useControlPlaneApi`, `lib/async-ui.ts`, `runtime-dashboard.ts` with its routes, and a 501 `cron` stub |
| Repo | `CHANGELOG.md` from an unrelated project; ~1.6 MB of committed minified third-party JS at the repo root; `ci.yml` stub; `requirements.txt` |

### 5.10 Test architecture masks the above

- Default Python suite:
  - Runs "Postgres-first but DB-less": `STATE_BACKEND=postgres` with persistence mocked, while the real Rust security guard is started.
  - Grants execution approval globally (`tests/conftest.py:175-182`), which hides the broken shell/git/supervised paths.
  - Runs only 4 of 109 dispatcher tests against the real policy gate.
- Coverage of the most important modules:

  | Module | Line coverage |
  |---|---:|
  | `__main__.py` | 4% (source-grep checks only) |
  | `control_plane/api.py` | 37% |
  | `queue_manager.py` | 58% |
  | `dashboard`, `runtime`, `memory/manager` | 0% |

- Rust sidecars other than security and bot-gateway are tested only against fakes.
- Web:
  - The Playwright suite (23 tests) runs in no workflow.
  - Test files are excluded from `tsc`; a scratch run found 52 errors.
  - BFF route handlers are mostly untested.
- Infrastructure invariants are enforced by string matching (`tests/test_installation_assets.py`), not by rendering the files.

## 6. Defects with structural root causes

This is a selection to show how the structure produces defects. The full register belongs in `TECHNICAL_DEBT.md` and the backlog.

| # | Defect | Label | Structural root cause |
|---|---|---|---|
| 1 | `/cancel` does not stop running tasks in the default configuration; cancelling a task kills the user's queue worker | V | Cancellation spread across queue globals, handlers and the runtime controller; `CancelledError` mishandled |
| 2 | Squad post-processing deadlocks on the non-reentrant per-user lock | V | Squad fan-out runs inside `_post_process` under a lock that also gates spawning and context prep |
| 3 | Retries re-run tools that have side effects | C | Four retry layers, none aware of completed tool calls |
| 4 | Stateless providers (Gemini, Ollama, OpenAI-compatible) get no in-session history, contradicting their capability warning | C | Provider capability metadata scattered |
| 5 | Agent `shell_execute`/`git_*` and supervised-mode writes always fail; the approval contextvar is never set in the queue worker | C | Five stacked approval gates; global test fixture |
| 6 | Dashboard approval routes cannot see worker approvals | C | Approval state in process memory across a process boundary |
| 7 | The two policy evaluators disagree on the same policy | V | Duplicate evaluators |
| 8 | Automatically materialised scheduled runs have no policy snapshot, so every recurring or one-shot job is blocked when it fires | V | Monkey-patched scheduler modules and circular lazy imports |
| 9 | Web-created routines never activate; deleted routines remain listed; routine names and connector, read-only and path controls are not persisted or enforced | V (activation), C (rest) | Reads through `dashboard_service` and writes through the worker runtime API, with different serializers; zod `passthrough` |
| 10 | Circuit breakers checked by `check_breaker` latch open forever; only Claude is protected | V | Check-then-skip pattern; resilience not applied uniformly |
| 11 | The SSRF guard admits `0.0.0.0` and IPv4-mapped IPv6; urllib OAuth paths have no private-IP check | V, C | Two HTTP stacks with separate guards |
| 12 | The read-only DB guard accepts side-effecting `SELECT` functions | V | Real severity depends on reachability; the tools review found no caller (**U**) |
| 13 | Resuming the runtime event stream returns 400 once event ids pass 1000 | V | |
| 14 | Memory recall is hard-filtered to the current task id, so earlier memories are effectively never recalled | C | Tests mock the gRPC engines; recall SQL never runs in tests |
| 15 | Knowledge retrieval runs against empty tables in primary mode; operator knowledge assets are never retrieved; the grounding gate may force `needs_review` as a result | C, U (last part) | No ingestion producer; a storage-mode layer that hides missing writers |
| 16 | The control-plane rate limiter keys on a client-supplied `X-Forwarded-For` | V | No trusted-proxy configuration |
| 17 | The OAuth relay route is unreachable because it requires a bearer token | V | Public-path lists duplicated |
| 18 | Hard delete orphans agent secrets and about 12 per-agent tables | V | 7 FKs across 130 tables |
| 19 | Unedited `.env.example` placeholders authenticated as break-glass owner | F `3f895ee` | |
| 20 | `koda uninstall` without `--purge` deleted data volumes | F `7b848cf` | |
| 21 | The prod overlay adds loopback ports but does not remove the public bindings | V | Untested overlays; exposure decision pending (D-10) |
| 22 | Squad-room SSE is cut every 10 s by the proxy timeout | V (Node experiment) | Bespoke SSE paths |
| 23 | Composer skill/MCP mentions are dropped by the backend; the generative-UI submit endpoint does not exist | C | Hand-mirrored contracts, no codegen |
| 24 | Squads: no-task coordinator modes leave the user without a reply; handoff never completes; delegation depth and cycle limits reset per hop; `agent_send` has no loop guard; budget auto-pause is advisory | C | Squad flow split across three god modules |
| 25 | Squad admin tools (elect, demote, Telegram bind) have no caller authorization | C | `agent_comm` category bundles admin operations |
| 26 | Approval tables use INTEGER Telegram IDs and are wiped across agents | C | DDL outside the migration registry |
| 27 | Bot-gateway acks updates that failed | C | Duplicate channel path |
| 28 | Every agent must be a Telegram bot: publish fails without `AGENT_TOKEN`, and the worker refuses to start | C | Worker lifecycle is a PTB Application |
| 29 | Control-plane outages appear as $0 or empty data | C | BFF synthesises HTTP 200 payloads |
| 30 | With `RUNTIME_ENVIRONMENTS_ENABLED`, light-task runs without a kernel terminal path may fail | U | Opt-in subsystem with no end-to-end test |

## 7. Target architecture (first cut)

### 7.1 Principles applied

From MISSION §5.2 and §12: a modular monolith by default, one implementation per concern, explicit typed contracts at module seams, a consistent error model, secure defaults, and incremental migration with no big-bang rewrite. Stable subsystems are kept as they are. A part is rewritten only when a verified defect or a measured cost justifies it.

### 7.2 When a separate process is justified

A component keeps or gets its own process only if it meets at least one of these tests with evidence:

1. It owns OS resources that must be isolated from, or outlive, Python workers (child processes, PTYs, browsers).
2. It is a trust boundary with different credentials or privileges.
3. A measured performance requirement exists that in-process Python cannot meet. This needs profiling data with realistic volumes.
4. Independent deployment or scaling is actually used.

| Component | 1 | 2 | 3 | 4 | Verdict |
|---|---|---|---|---|---|
| runtime-kernel | yes | yes (agent tool code runs apart from the master key) | n/a | no | **Keep process** |
| agent worker per agent | partly (per-agent env and secrets) | yes | no | no | **Keep** the current model |
| web (Node) | no | yes (holds the sealed session) | n/a | no | **Keep** (different runtime) |
| security, memory, retrieval, artifact, policy-engine, bot-gateway | no | no (unauthenticated, same DSN) | no evidence (≤400-row lexical scans, empty retrieval tables) | no | **Fold into Python or remove** |

### 7.3 Target topology

| Process | Runtime | Responsibility | Change from today |
|---|---|---|---|
| `web` | Node | UI, BFF, WS relay | Trim dead code; one fetch/SSE layer |
| `app` | Python | Control-plane API, reconcile and publish | Domain routers and services; no cluster mode |
| agent worker ×N | Python (kernel child) | Channel intake, execution, tools, memory, scheduling, runtime API | Telegram optional; in-process security, memory and artifact modules |
| `runtime-kernel` | Rust | Worker supervision, environments, terminals, browser | UDS plus auth token; explicit restart semantics |
| `postgres` | pg16 + pgvector | All durable state | One migration registry; typed columns; FKs |
| `seaweedfs` (+ init) | S3 | Blobs | Kept; making it optional for small installs is deferred |

Default containers go from 10 to 6 (5 services plus the S3 init job). `app` and `runtime-kernel` run from one image with two commands. Removed: `security`, `memory`, `retrieval` (or reimplemented in Python, per D-6), `artifact`, `policy-engine`, `bot-gateway`, the PyO3 command guard, and most of `koda/internal_rpc` (8.3k lines).

### 7.4 Python module map

```
koda/
  app/            entrypoints: worker (__main__), supervisor, cli; wiring only
  config/         typed Settings, loaded once, passed explicitly; one key registry
  state/          db.py (one pool per process), migrations/NNN_*.sql, async repositories per domain
  security/       command guard, path resolver, env sanitiser, redactor, SSRF guard (one each)
  channels/
    telegram/     PTB adapter: central auth filter, commands, callbacks -> execution.submit()
  execution/
    intake.py     submit(TaskRequest) for every origin (chat, dashboard, scheduled, squad, child, retry)
    worker.py     per-user FIFO, cancellation, startup recovery
    context.py    prompt/context assembly (memory, knowledge, skills, budget)
    provider_executor.py   fallback chain, one retry and error-classification policy
    agent_loop.py tool calls via tools.execute(), resume
    delivery.py   text, voice, artifacts, dashboard stream
    hooks.py      post-turn hook registry (squads, memory extraction, cost)
  providers/
    registry.py   catalog, models, capabilities, timeouts, retry classes, auth modes
    cli/          shared subprocess base + claude/codex/gemini parsers
    openai_compatible.py   all HTTP providers, including Ollama, llama.cpp, MLX
  tools/
    catalog.py    single declaration per tool: handler, read/write, category, policy resource
    policy.py     the only execution-policy evaluator (worker and control plane)
    approvals.py  Postgres-backed requests and fingerprinted grants
    handlers/     one module per family (files, shell, git, web, browser, jobs, squad, ...)
    mcp/          one server-start path that applies isolation; client
  memory/         extraction, SQL store with Postgres FTS, one recall scorer
  knowledge/      ingestion + pgvector retrieval, only if in scope (D-6)
  squads/         threads, tasks, one routing pipeline, one durable dispatch, post-turn hook, tools
  scheduling/     job domain, dispatcher, runs; no shims or monkey-patching
  runtime_env/    isolated environments + kernel client, only if in scope (D-8)
  control_plane/
    api/          one router module per domain, thin handlers, one error envelope
    services/     agents_publish, secrets, providers, integrations, policies, quality, dashboard, workspaces
    auth/         operator auth (unchanged contract, see docs/security/authentication.md)
  observability/  metrics (provider-labelled), logging; tracing only once spans exist
```

### 7.5 Dependency rules

1. Every intake path (Telegram, dashboard, scheduler, squads, control-plane retry) calls `execution.submit()` and nothing deeper.
2. `execution` depends on `providers`, `tools`, `memory`, `knowledge` and `state`. Squads, memory extraction and cost accounting attach through `execution.hooks`, so `execution` never imports squad internals.
3. `tools` depends on `security` and `state`, never on `execution` internals.
4. Only `state/migrations` contains DDL. Domain packages own their repositories but not the schema.
5. `control_plane` never reads worker memory. Communication across processes goes through Postgres, using rows plus `NOTIFY` where low latency is needed, or through the worker runtime HTTP API.
6. `config` is the only module that reads `os.environ`. A CI check rejects env reads elsewhere and keys missing from the registry.
7. The only Rust boundary is the runtime-kernel gRPC API over UDS with a token.

### 7.6 Key contracts to introduce

| Contract | Replaces |
|---|---|
| `TaskRequest` (typed origin, options, policy snapshot ref) | Raw `dict`s with underscore flags, 9 enqueue variants |
| `ProviderResult` / `ProviderError(kind, retryable)` | Adapter dicts with `_error_kind`/`_retryable`, regex and keyword classification |
| `ToolSpec` (catalog entry) | 5 catalogs and the drift detector |
| `PolicyDecision` and `Grant` (one evaluator, persisted approvals) | 2 evaluators, 5 gates, in-memory approval state |
| One HTTP error envelope `{"error": {"code", "message", "user_action?"}}` | Three backend shapes and blanket `KeyError`→404 / `ValueError`→400 mapping |
| OpenAPI with real response schemas, the source for generated web types | 217 of 304 operations with generic responses, hand-mirrored TS types |

### 7.7 Web target

Keep the Next.js BFF boundary. Changes:

- **Fetch layer:** one HTTP client and error parser that match the backend envelope; React Query query tiers only; one SSE hook; one route registry for sidebar, topbar and palette.
- **Design system:** one button system and one error/empty state.
- **Styling:** feature styles colocated, with tokens and base styles in `globals.css`.
- **i18n:** keyed i18next only.
- **Outages:** the BFF returns 503 instead of synthetic 200 payloads (D-15).
- **Channel secrets:** validation moves to the backend, so the web tier stops handling decrypted channel secrets.
- **Cleanup:** remove unreachable code first.

### 7.8 Delivery target

- One Python image (app plus kernel binary) and one cached Rust build stage for the kernel.
- Generate the release compose bundle from the base file plus overrides, and test both by rendering them.
- Make loopback bindings the default once D-10 is approved.
- Pin provider CLI versions; add `rust-toolchain.toml`; use the same Node version in CI and in images.
- Make release workflows reuse PR workflows through `workflow_call`.
- Scanning: one SCA tool per ecosystem, plus CodeQL, gitleaks and Trivy on every shipped image.
- Run Playwright in CI against the docker-smoke stack.

## 8. Decisions per component

Decision vocabulary from MISSION §5.3. "Pending D-n" means the decision shown is the default proposal, waiting on the open question in section 11. Effort: S (≤1 day), M (days), L (week+).

### 8.1 Execution and providers

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| `queue_manager.py` | simplify | Split into `execution/*` along the seams in 7.4; re-export old names until callers move | 9,438 lines; three ~1k-line functions | L |
| Enqueue variants (9) | consolidate | `submit(TaskRequest)` | Inconsistent checks | M |
| Per-user FIFO worker | keep, repair | Lock guards user state only; cancellation leaves the worker alive | Defects 1, 2 | M |
| Lease and janitor | simplify (pending D-1) | Startup recovery plus guarded status transitions | Single process holds the queue | M |
| Per-user semaphore | remove | | Never limits | S |
| Retry layers | simplify | One policy in `provider_executor`; completed tool calls are never replayed | Defect 3 | M |
| tenacity | remove | | Single consumer | S |
| Circuit breaker | repair | Uniform per-provider breaker with working half-open | Defect 10 | S |
| `AgentTurn` | simplify | Plain audit-payload function | Audit-only consumer | S |
| RunGraph store and duplicate routes | simplify | Derive from the trace on read; one route | ~1.7k lines | M |
| Context governance (main runs) | simplify | Keep for child runs only | Report-only | S |
| Grounding gate | keep, repair | Skip when the corpus is empty or knowledge is out of scope | Defect 15 (**U**) | S |
| Provider metadata | consolidate | `providers/registry.py` | ~7 modules | L |
| CLI adapters | consolidate | Shared subprocess base plus per-CLI parsers | Duplicated helpers across 4 adapters | L |
| Ollama runner | replace | OpenAI-compatible profile | Blocking urllib, fake streaming | M |
| OpenAI-compatible runner | keep | | Already consolidated | — |
| Stateless-provider history | repair (pending D-13) | Transcript replay in `context.py` | Defect 4 | M |
| `CLAUDE_EXECUTION` metric | repair | Provider-labelled metric | Misnamed | S |

### 8.2 Tools, policy, approvals, security, MCP

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| `tool_dispatcher.py` | simplify | `tools/handlers/<family>.py`; small core | 5,518 lines | L |
| Tool catalogs (5) | consolidate | `tools/catalog.py`; prompt, dispatcher, policy and UI derive from it | Measured drift | M |
| Policy evaluators (2) | consolidate (pending D-5) | One evaluator shared by worker and control plane | Defect 7 | M |
| Policy stores (8) | consolidate | Execution policy as the only surface; migrate the rest; deprecate legacy routes | Three already marked legacy | L |
| Approval gates (5) | simplify | Decision → request → fingerprinted grant → execute | Defect 5 | M |
| Approval state | repair | Postgres, readable by both processes; drop unexecutable pending-op persistence | Defect 6 | M |
| Shell blocklist copies | consolidate | `security/command_guard.py` in the worker; the kernel keeps its linked check for commands it runs; documented as a guard, not a sandbox | Up to 4 checks, easy to bypass | M |
| Safe-path, redaction, SSRF | consolidate | One implementation each in `security/` | 4, 3 and 2 copies; defect 11 | M |
| urllib in runtime paths | replace | aiohttp | Blocking, separate guard semantics | M |
| Provider-native permission bypass | decision (D-4) | Map Koda policy onto provider permission modes, or run provider CLIs only in kernel-isolated environments; document the trust boundary either way | Gates cover only `<agent_cmd>` | L |
| MCP server start (7 sites) | consolidate | One start function that applies isolation | | M |
| MCP isolation settings | repair or remove (pending D) | Enforce, or drop the fields and UI | Stored, never applied | M |
| Hand-rolled MCP client | replace (evaluate) | Official MCP Python SDK, after a live check against an HTTP server | No session/SSE handling (**U** compatibility) | M |
| Duplicate MCP catalog, decrypt helpers | remove, consolidate | Keep `koda/integrations/mcp_catalog.py` | Test-only copy | S |
| `DBManager` and SSH tunnels | remove (pending) | | Started at boot, no caller | S |
| Script library search | simplify | Cache embeddings; move the reranker off the loop or drop it | Re-embeds on every search | S |
| `/fetch` vs `/curl` | consolidate | | Identical | S |
| Admin role for `/shell`, `/docker`, `/pip` | repair (pending D-12) | Use the existing `is_admin`, or remove it | Unused guard | S |

### 8.3 Channels

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| Telegram via PTB | keep, repair | `channels/telegram` calls `submit()`; central auth filter; no lock-holding handlers | Bot-wide stalls (**C**) | M |
| Worker bound to PTB lifecycle | repair (pending D-2) | Worker runs without Telegram; Telegram enabled when a token exists | Defect 28 | M |
| 8 unwired adapters, `ChannelManager`, UI credential forms, optional SDKs | remove (pending D-3) | | ~1.9k lines, never started, 0 tests | S |
| bot-gateway | remove | | Duplicate path; defect 27 | S |

### 8.4 Memory and knowledge

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| Rust memory engine | consolidate into Python (pending D-7) | SQL plus Postgres FTS in `memory/store.py`; single writer to `napkin_log`; curation projections in Python | Lexical scoring of ≤400 rows; two writers; no-op dedupe | L |
| Recall scoring (2) | consolidate | One Python scorer, tested against real Postgres | Neither tested on real data | M |
| Recall filter | repair | Task, query and session links become additive sources | Defect 14 | S |
| Namespaces/sensitivity, embedding queue, dedupe RPC | remove | | Never set, never produce | S |
| `pre_query` vs `pre_query_details` | consolidate | | Duplicate | S |
| Knowledge storage-mode layer | simplify | Remove OFF/local modes; surface write failures | Always-false branches | M |
| Knowledge v2 retrieval (Rust) and `KnowledgeManager` | replace in Python or remove (pending D-6) | If in scope: Python ingestion plus pgvector SQL ported from the Rust engine, with its tests as the spec. If not: remove the stack, including per-query embeddings | Empty tables in primary mode | L |
| Embedding dimension | repair (D-6) | One canonical model and dimension | 1024 configured vs 384 model default (**U** risk) | S |
| Neo4j config | remove | | No references | S |
| `task_policy_defaults.py` location | keep | Move with `tools/policy` later | Low value now | S |
| `agent_id` casing | repair | One canonical form plus a data migration | Split casing | S |

### 8.5 Squads, skills, workflows

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| Squad core (threads, tasks, CAS, obligations, access) | keep | | Bounded loops; coherent design | — |
| Inbound routing (2 copies) | consolidate | `squads.routing.route_inbound()` for Telegram and web | Diverging | M |
| Dispatch transports (3) | simplify | One durable path: Postgres row plus `NOTIFY` to the target worker inbox; drop in-process execution of another agent's turn | Unclear semantics; whether it loads the target's spec and secrets is **U** | M |
| Squad code in `queue_manager`, `tool_dispatcher`, `api.py` | consolidate | Post-turn hook, `tools/handlers/squad.py`, one router | ~3k lines spread out | M |
| asyncpg pools (10) | consolidate | Shared pool from `state/` | Connection fan-out | M |
| LISTEN/NOTIFY (2) | consolidate | One reconnecting listener | One does not reconnect | S |
| System-event row scatter | simplify | One routing record per inbound message | Bloats history and prompts | M |
| `agent_comm` category | repair | Separate `squad_admin` category with caller authorization | Defect 25 | S |
| Delegation limits, `agent_send` guard, budget pause | repair | Carry depth and visited set across hops; enforce budget | Defect 24 | M |
| In-memory bus backend | remove | Reject at startup when squads are enabled | Non-functional with one process per agent | S |
| `squads/__init__` re-exports (~120) | simplify | | Hides coupling | S |
| Workflow engine | remove (pending D-9) | | No persistence or UI; overlaps agent loop and squads | S |
| Legacy plugin manifest and registry | consolidate | KodaSkill packages only | Two manifest systems | M |
| Skill package code loading | repair (decision) | Declare packages as trusted code explicitly, or execute them out of process | A denylist is not a sandbox | M |
| Skill embedding index per turn | repair | Cache per spec version | Re-embeds every turn | S |

### 8.6 Scheduling and runtime services

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| `scheduled_jobs` + dispatcher + runtime handler | consolidate | `scheduling/` with explicit imports | Defect 8 | M |
| `scheduler.py`, `cron_store.py` | remove | | No-op shims | S |
| Background loops (3 mechanisms) | consolidate | `lifecycle_supervisor` with backoff, visible in health | Inconsistent | M |
| Isolated runtime environments (~6k lines) | pending D-8 | If kept: split the controller into workspace, terminal, browser and checkpoint modules. If not: remove behind the flag | Off by default | L |
| `RuntimeStore` passthrough, `RecoveryManager` plan | remove, simplify | | Erases typing; identical actions | S |
| Runtime event dual persistence | simplify | Postgres only | Duplicate writes | S |
| Semantic cache (3 strategies) | simplify | Exact hash plus one embedding path; FAISS only with eval evidence | Undeclared dependencies | M |
| `cache_config.py`, `confidence_config.py` | consolidate | Into `config/` | Centralisation rule | S |
| Fallback shims for prometheus and pybreaker | remove | | Hard dependencies | S |
| Tracing | simplify | Keep init; remove unused propagation helpers | One span | S |
| Evals, quality cockpit | keep | Deduplicate helpers (`as_record`, `stable_digest`, ...) | In good shape | S |
| Improvement proposals | simplify (pending D-16) | Rename `apply` to match its effect, or remove the state machine | Ledger-only | M |
| Webhook/event_wait/snapshot tools | remove (pending) | | Non-functional | S |
| Audit | keep, repair | Working retention | Purge targets missing tables | S |
| Voice (TTS/STT) | keep | Document it; add integrity checks for model downloads | Undocumented, heavy dependencies | S |

### 8.7 Control plane

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| `ControlPlaneManager` | consolidate | Domain services listed in 7.4 | 241 methods, 15,061 lines | L |
| `api.py` | simplify | Routers per domain | 5,850 lines | M |
| Duplicate MCP and legacy eval routes | remove | After confirming no external clients (D-5) | Web uses neither | S |
| Per-handler re-auth | remove | Use the middleware context | Double reads and writes | S |
| `database.py` shim | remove | Direct repositories | Test-only indirection | M |
| `ensure_seeded` on the hot path | simplify | One-time migration | Runs every 5 s | S |
| Error model | repair | One envelope (7.6) | Masks bugs, leaks internals | M |
| Operator auth | keep, repair | Trusted-proxy setting for XFF; one public-path list shared with the web; PAT scopes pending D-12 | Defects 16, 17 | M |
| Cluster mode | remove (pending D-1) | | Single-owner product; unauthenticated endpoints | M |
| `control_plane/settings.py` | consolidate | Into `config/` | Duplicate loader | M |
| Heavy GETs (N+1) | simplify | | ~20 queries per `get_agent` | M |
| Hard delete | repair (pending D-11) | FKs with cascade, or archive by default | Defect 18 | M |
| Secrets embedded in snapshots | repair | Reference secrets by id; resolve at worker start | Rotation requires republish | M |
| OAuth relay | repair or remove | Depends on the current Claude CLI redirect behaviour | Unreachable | S |
| OpenAPI | keep, repair | Real response schemas and security markings | 217 of 304 operations generic | M |
| Duplicate kernel clients | consolidate | One client | Two channels and breakers | S |

### 8.8 State and schema

| Component | Decision | Target | Rationale | Effort |
|---|---|---|---|---|
| `KnowledgeV2PostgresBackend` as app-wide store | replace | `state/db.py` plus `state/migrations/` plus per-domain repositories | 5,296 lines in the wrong package | L |
| Inline migrations with two owners | repair | Numbered SQL files, `schema_migrations`, advisory lock, one runner | Forward-only strings | M |
| Runtime-created tables (approvals, artifacts) | consolidate | Into the registry | Defect 26 | S |
| `run_coro_sync` bridge | replace | Async repositories on async paths; sync only for the CLI | Blocks loops | L |
| Column types and FKs | repair (incremental) | TIMESTAMPTZ, BOOLEAN, BIGINT Telegram IDs, FKs on hot relations | 7 FKs, 95 TEXT timestamps | L |
| SQLite branches, `STATE_BACKEND` | remove | | Dead | S |
| JSON fallbacks in `STATE_ROOT_DIR` | remove (pending D) | | Unknown external consumers | S |
| One schema for all agents | keep | `agent_id` scoping with canonical casing | Adequate | — |
| Master key handling | repair | Separate HMAC key; documented backup; a rotation path that is actually called | Reuse; no backup tooling | M |

### 8.9 Rust workspace

| Crate | Decision | Rationale | Effort |
|---|---|---|---|
| `koda-runtime-kernel` | keep, repair (UDS plus token, restart semantics, split `server.rs`) | Owns OS resources | M |
| `koda-security-service` | replace with the Python `security/` module | Pure functions over a network hop; availability risk | M |
| `koda-security-core` | keep (linked by the kernel only) | Kernel-side command check | — |
| `koda-memory-engine` | consolidate into Python (pending D-7) | See 8.4 | L |
| `koda-retrieval-engine` | pending D-6 | See 8.4 | L |
| `koda-artifact-engine` | consolidate into Python | Duplicate S3 access; per-request DDL; hard dependency | M |
| `koda-policy-engine` | remove | Not configurable | M |
| `koda-bot-gateway` | remove | Duplicate of PTB path | S |
| `koda-command-guard` | remove | Never shipped | S |
| `koda-postgres`, `koda-proto`, `koda-observability` | simplify (shrink with consolidation) | Fewer consumers | S |

### 8.10 Configuration

| Component | Decision | Target | Effort |
|---|---|---|---|
| Import-time constants in `koda/config.py` | replace | Typed `Settings` loaded once and passed explicitly; tests construct `Settings` | L |
| Env surface (~381–606 keys) | simplify | Classify every key as an operator knob (documented in `.env.example` and docs), publish-time plumbing (generated, not hand-edited) or dead (removed); CI check enforces the registry | L |

### 8.11 Web

| Component | Decision | Target | Effort |
|---|---|---|---|
| BFF pattern | keep | | — |
| Unreachable code (71 files), `runtime-dashboard.ts` and routes, `async-ui.ts`, nested `ToastProvider` | remove (audit UI pending decision) | | M |
| Generative-UI blocks | remove (pending D-14) | | S |
| Synthetic outage payloads | simplify (pending D-15) | 503 plus one unavailable state | S |
| Fetch and error helpers | consolidate | One client matching the backend envelope | M |
| Caching policies and query conventions | consolidate | Query tiers only | M |
| Stabilisation hooks | simplify | Use React Query built-ins | M |
| SSE loops (4) | consolidate | One hook; fix the 10 s proxy timeout | M |
| Navigation metadata (3), redirect stubs | consolidate | One route registry; redirects in `next.config` | S |
| Button systems, error states, `error.tsx` copies | consolidate | | L |
| `globals.css` and reset hacks | simplify | Tokens and base global; features colocated; decide on the shadow reset | L |
| i18n layer | simplify | Keyed i18next only; retire `tl()` and regex replacement gradually | L |
| Channel validation and web-tier secrets | consolidate | Backend validation endpoints | M |
| Hand-mirrored TS types | replace (incremental) | Generated from OpenAPI once schemas are real | M |
| three.js orb, product tour | pending D-14 | CSS/SVG glyph; remove or finish the tour | S–M |
| Agent ID and port allocation in the client | simplify | Server-side allocation; 409 on collision | S |
| Components over 1k lines | simplify | Split when touched | L |

### 8.12 Delivery and tests

| Component | Decision | Target | Effort |
|---|---|---|---|
| Default stack (10 containers) | simplify | 6 (5 services plus init), following 8.9 | L |
| Source vs release compose | consolidate | Release generated from base; rendered-config tests | M |
| Overlays | repair or remove | Prod loopback (D-10); cluster removed; observability only once metrics are reachable | M |
| Dockerfiles | consolidate | One Python image; one cached Rust stage; drop redundant `protobuf-compiler` | M |
| Provider CLI pins, toolchain skew | repair | Pinned versions; `rust-toolchain.toml`; matching Node | S |
| `release.yml` duplication | consolidate | Reusable workflows | M |
| Scanners | simplify | One SCA per ecosystem plus CodeQL, gitleaks, Trivy on all images | M |
| `requirements.txt`, duplicate dev deps, empty extra | remove, consolidate | | S |
| Committed vendor bundles, foreign `CHANGELOG.md` | remove (history purge pending D-17) | | S |
| npm CLI installer | keep, repair | | — |
| Mocked orchestration tests | repair | After the split: real Postgres plus a fake provider at the adapter boundary; remove the global approval fixture | L |
| Operator-auth SQL-string fake | replace | Real Postgres tests | M |
| Playwright, web test type-check | repair | Run in CI; add `tsc` over tests | M |
| Dead test tooling (live-gate script, unused markers, bench scripts, testcontainers branch) | remove | Add `--strict-markers` | S |

## 9. Migration sequence

This is a first cut; `MASTER_PLAN.md` will break it into tasks. Each step keeps the CLAUDE.md validation gates green and ships independently. The verified security and data-integrity defects in section 6 are handled first through the backlog, in parallel with step 1.

| Step | Content | Entry condition | Why this order |
|---|---|---|---|
| 1. Safety net and dead weight | Real-Postgres characterisation tests for execution, approvals, scheduling, memory recall and squads. Remove the global approval fixture. Playwright and web `tsc` in CI. Delete code with zero consumers (5.9) | Postgres CI job green | Refactors need tests that run the real paths; deletion shrinks the surface first |
| 2. State foundation | Extract migrations into `state/migrations`; register runtime-created tables; one pool per process; typed `Settings` for DSNs; async repositories on the queue and control-plane hot paths | Step 1 | Every later step touches persistence |
| 3. Execution core | `TaskRequest` and `submit()`; move code into `execution/*` without behaviour change, then fix cancellation, locking and retries; provider registry; post-turn hooks; squads leave `queue_manager` | Steps 1–2 | Largest god module; defects 1–4 |
| 4. Tools, policy, approvals, security | Single catalog; one evaluator (dual-evaluate and log diffs before switching); Postgres approvals; `security/` module; one MCP start path | Step 3 (agent loop seam) | Defects 5–7, 11 |
| 5. Sidecar consolidation | In order: security in-process (lowest risk); artifact; memory (after recall SQL tests); retrieval per D-6; remove policy-engine, bot-gateway and command-guard; merge images; compose from 10 to 6 containers; regenerate the release bundle | Steps 2 and 4 | Python modules must own the SQL before the sidecars go |
| 6. Control plane | Domain routers and services; error envelope; policy-store migration with deprecation of legacy routes; cluster-mode removal; delete semantics | Step 4 (policy evaluator) | Depends on the single policy surface |
| 7. Web | Fetch/SSE/query consolidation, design-system consolidation, i18n simplification, generated types | Can start after step 1; API contract changes are coordinated with step 6 | Independent runtime |

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Splitting `queue_manager` changes behaviour that tests do not cover | High | Step 1 first; move code before changing it; characterisation tests on real Postgres |
| Policy-store consolidation changes effective permissions | High | Dual evaluation with diff logging; fail closed; operator-visible migration report |
| Schema migrations (casing, types, FKs) on existing installs | High | Forward migrations with backfill tested on a copy; documented backup, including the master key |
| External API clients depend on legacy routes | Medium | Mark deprecated in OpenAPI; deprecation window; check access logs where available |
| Porting Rust SQL services loses performance | Low–medium | Profile with realistic row counts first; keep the Rust tests as the port's spec |
| Async conversion introduces ordering or concurrency bugs | Medium | One repository at a time; per-user FIFO ordering preserved and tested |
| Removing channel adapters, the tour or generative UI conflicts with product scope | Medium | Wait for D-3 and D-14 |
| Making Telegram optional changes worker start-up | Medium | Behind a flag first; supervisor and worker start-up tests |
| Single image enlarges the `app` container's footprint | Low | Same contents as today's kernel image; separate commands and users per container |

## 11. Decisions needed

The proposed default is what this document assumes until the decision is made.

| ID | Question | Proposed default | Affects |
|---|---|---|---|
| D-1 | Is more than one worker process per agent, or a multi-host/cluster deployment, ever required? | No: single host, one worker per agent | Lease/janitor, cluster mode, gRPC split |
| D-2 | Must every agent be a Telegram bot? | No: Telegram is optional per agent | Worker lifecycle, publish checks |
| D-3 | Which channels beyond Telegram are in scope? | None; remove the 8 adapters and their UI forms | Channels, web, dependencies |
| D-4 | Is unrestricted provider-native tool use intended, with an external sandbox assumed? | Define the trust boundary explicitly; map policy to provider modes or confine to kernel environments | Security posture, docs |
| D-5 | Which policy evaluator is authoritative, and can legacy policy and MCP route families be retired? | `services/execution_policy.py` semantics as the base, validated by diffing; retire legacy after deprecation | Tools, control plane, API clients |
| D-6 | Is knowledge v2 retrieval in scope, and who produces chunks/embeddings? Which embedding model and dimension? | Decide scope first; if in scope, Python ingestion and retrieval | Retrieval engine, grounding gate |
| D-7 | Keep the Rust memory engine or move memory to Python SQL? | Python SQL with Postgres FTS | Memory, Rust workspace |
| D-8 | Are isolated runtime environments (`RUNTIME_ENVIRONMENTS_ENABLED`) in scope? | Keep gated; decide before investing in the controller split | ~6k lines, kernel API |
| D-9 | Squads on by default? Keep the workflow engine? | Squads opt-in until the end-to-end flow passes on Postgres; remove workflows | Squads, tools |
| D-10 | Bind 3000 and 8090 to loopback by default? (Already raised in EXECUTION_STATUS.md) | Yes, with an explicit opt-in for direct LAN access | Compose, docs |
| D-11 | Hard delete vs archive for agents? | Archive by default; hard delete purges all per-agent tables | Schema FKs, control plane |
| D-12 | Do personal tokens need scopes? Should dangerous commands require an admin role? | Read-only vs owner scopes; admin gate for shell-type commands | Auth, handlers |
| D-13 | Should stateless providers replay recent transcript on each turn? | Yes, within the prompt budget | Context builder |
| D-14 | Web scope: generative UI, product tour, WebGL orb, 5 locales | Remove generative UI and the orb; decide tour; keep locales with keyed i18next only | Web |
| D-15 | On control-plane outage, synthetic 200 payloads or 503? | 503 plus a visible unavailable state | BFF, every page |
| D-16 | Should improvement proposals ever apply changes automatically? | No; rename the state to reflect ledger-only acceptance | Quality features |
| D-17 | Purge the vendor bundles and foreign `CHANGELOG.md` from git history? | Licensing review decides; remove from HEAD regardless | Repository |
| D-18 | Observability topology: aggregate metrics in the control plane, or expose worker metrics ports? | Control-plane aggregation endpoint; drop the overlay until data flows | Observability, compose |
| D-19 | Is the direct `python -m koda --agent-id` launch (no supervisor) supported? | No; supervisor-only start-up | Config hydration order |
| D-20 | Should work-dir artifact auto-discovery scan shared or home directories? | No; task workspace only | Artifact scan, cross-task leakage |
