# System Inventory

Snapshot of the repository at commit `7b848cf` (branch `claude/dreamy-cerf-mhvbwn`), 2026-11-14.
Part of the consolidation mission ([MISSION.md](MISSION.md)); read together with
[EXECUTION_STATUS.md](EXECUTION_STATUS.md), [QUALITY_BASELINE.md](QUALITY_BASELINE.md) and
[VALIDATION_REPORT.md](VALIDATION_REPORT.md).

This file records what exists and how healthy it is. It is not a plan. Dispositions in the
dependency tables are proposals for the master plan, not decisions.

## 1. Scope and evidence

Sources:

- 13 specialist subsystem reviews: core-execution, tools-mcp-sandbox, runtime-scheduling-services,
  control-plane, memory-knowledge, multi-agent, state-rpc-rust, web-shell-design, web-features-a,
  web-features-b, devops-security-supply, tests-quality, product-scope.
- Read-only inventory commands run for this document (`ls`, `wc`, `grep`, manifest reads, `git ls-files`).

Evidence labels used below:

| Label | Meaning |
|---|---|
| `inv` | Checked for this document with read-only commands at `7b848cf` |
| `run` | A specialist confirmed it by running code, tests, probes, simulations or rendered config |
| `read` | A specialist found it by reading code; not executed |
| `unverified` | Inferred, or flagged by the specialist as not checked; needs confirmation before acting |

Rows without a label come from `read` unless stated otherwise.

## 2. At a glance

| Item | Value | Evidence |
|---|---|---|
| Python backend `koda/` | 358 files including generated gRPC stubs; ~172k lines excluding them | `inv` |
| Largest Python modules | `control_plane/manager.py` 15,061; `services/queue_manager.py` 9,438; `control_plane/api.py` 5,850; `services/tool_dispatcher.py` 5,518; `knowledge/v2/postgres_backend.py` 5,296; `services/runtime/controller.py` 4,035 | `inv` |
| Web app `apps/web/src` | 707 TS/TSX files, ~169k lines; `globals.css` 10,478 lines | `inv` |
| Rust workspace `rust/` | 11 workspace crates (7 binaries, 4 libraries) + 1 excluded PyO3 crate; ~19.8k lines `.rs` | `inv` |
| Protobuf | 8 packages, 8 `.proto` files, all `v1` | `inv` |
| Control-plane HTTP routes | 302, matched 302/302 by `docs/openapi/control-plane.json` | `run` |
| Postgres schema | One database, one schema (`knowledge_v2`), ~130 tables, 50 inline migrations, 7 foreign keys | migrations `inv`; tables and FKs `read` |
| Default containers | 10 (`docker-compose.yml`), plus 2 opt-in profiles and a 4-container observability overlay | `inv` |
| CI | 8 workflows, 2,547 lines; `release.yml` alone is 1,214 lines | `inv` |
| Python tests | 326 `test_*.py` files; 4,897 passed, 200 skipped at HEAD; 61% line coverage (gate 53.5%) | files `inv`; results from VALIDATION_REPORT |
| Postgres-marked tests | 188; 186 passed, 2 skipped with a DSN; new CI job has not run yet | `run` |
| Web tests | 157 vitest files, 692 tests; Playwright 23 tests in 11 files, not in CI | `run` |
| Env-driven settings | ~381-387 read in `koda/config.py`; ~606 env vars repo-wide | `read` (counts differ, see section 8) |

## 3. Repository structure

### 3.1 Top level

| Path | Contents | Notes |
|---|---|---|
| `koda/` | Python backend: control plane, agent worker, services, state, RPC clients | section 3.2 |
| `apps/web/` | Next.js operator console | section 3.3 |
| `packages/cli/` | `@openkodaai/koda` npm installer CLI and release bundle | section 3.4 |
| `rust/` | Cargo workspace of gRPC sidecars and shared libraries | section 3.5 |
| `proto/` | gRPC contracts | section 3.6 |
| `tests/` | pytest suite, fixtures, Postgres fixtures, benchmarks | section 3.13 |
| `scripts/` | Release, install, smoke, seed, migration and CI helper scripts | section 3.8 |
| `docs/` | Architecture, install, operations, security, squads, OpenAPI, engineering | section 3.14 |
| `plugins/example-hello/` | Example legacy plugin (`plugin.yaml`, `handlers.py`) | |
| `examples/skills/safe-readonly/` | Example skill package | |
| `Dockerfile*` (8), `docker-compose*.yml` (5) | Images and orchestration | section 3.11 |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | Python manifests; `requirements.txt` mirrors runtime deps | section 3.15 |
| `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` | pnpm workspace (`apps/*`, `packages/*`), 8 security overrides | |
| `buf.yaml`, `buf.gen.yaml` | Proto lint and Python codegen | `buf.yaml` is `v1beta1` (deprecated) |
| `launcher.py` | Second entry to `run_supervisor()` | duplicates the `koda` console script |
| `koda.service.example` | systemd unit running `docker compose up -d` in `/opt/koda` | |
| `main-BwqrdVu3.js`, `app-server-manager-signals-BEaGjuc8.js` | 1.21 MB and 408 KB minified third-party bundles, tracked | section 3.15 |
| `CHANGELOG.md` | Changelog of `@googleworkspace/cli`, not Koda | `inv` |
| `AGENTS.md`, `CLAUDE.md` | Agent guides; near-identical, differ from line 73 | `inv` |

### 3.2 Python backend (`koda/`)

| Package | Files | Lines | Role | Notes |
|---|---:|---:|---|---|
| top-level modules | 10 | 8,258 | `__main__.py` (worker entry, ~60 PTB commands, ~45 callbacks), `config.py` (1,443), `agent_contract.py` (2,526), `provider_models.py` (2,311), `agent_turn.py` (672), `auth.py`, `logging_config.py` | `startup_validator.py` (118) is dead |
| `services/` | 108 | 64,656 | Queue orchestration, provider runners, tool dispatcher, MCP stack, scheduler, runtime-environment controller and API, caches, voice, evals, quality, health, metrics | `queue_manager.py` is the orchestration spine; 171 functions |
| `control_plane/` | 26 | 32,410 | aiohttp operator API (302 routes), `ControlPlaneManager` (241 methods), supervisor, operator auth, crypto, rate limit, cluster mode, runtime access broker | runs in the supervisor process |
| `knowledge/` | 29 | 12,436 | Knowledge v2 retrieval, judge, grounding gate, runbook governance | `v2/postgres_backend.py` owns the schema for the whole app |
| `squads/` | 24 | 9,875 | Threads, tasks with CAS claims, reply obligations, coordinator, router sweeper, Telegram forum binding | ~3k more squad lines live in `queue_manager.py`, `tool_dispatcher.py`, `squad_handlers.py`, `control_plane/api.py` |
| `state/` | 15 | 8,250 | Sync store facades over the shared asyncpg backend | ~226 `run_coro_sync` call sites |
| `handlers/` | 10 | 7,191 | Telegram command and callback handlers | 6 modules excluded from mypy |
| `utils/` | 24 | 6,530 | Shared helpers (embeddings, approvals, paths) | |
| `memory/` | 22 | 5,892 | Conversational memory extraction, recall, procedural memory | recall goes through Rust `memory` sidecar |
| `internal_rpc/` | 38 | 4,696 | gRPC clients for 7 Rust services; `generated/` stubs (excluded from line count) | mixes sync and `grpc.aio` clients |
| `channels/` | 16 | 3,212 | Telegram gateway contract plus 9 other adapters, `ChannelManager`, webhook dispatcher | only Telegram is started |
| `skills/` | 8 | 2,859 | Skills v2 registry, selector, KodaSkill packages | per-turn re-embedding of all skills |
| `integrations/` | 3 | 2,644 | MCP catalog and custom MCP registry | second MCP catalog lives in `control_plane/mcp_catalog.py` |
| `agents/` | 6 | 1,419 | Inter-agent message bus, LISTEN/NOTIFY listener | memory and Postgres backends |
| `workflows/` | 4 | 333 | In-memory sequential tool-workflow engine | no persistence, UI or run-graph link |
| `plugins/` | 4 | 308 | Legacy in-process plugin registry | now only a backend for skill packages; unsandboxed |
| `snapshots/` | 3 | 219 | Snapshot helpers | |
| `observability/` | 2 | 193 | OpenTelemetry scaffold | one span in the codebase |
| `cli/` | 2 | 164 | `migrate` subcommand | |
| `runtime/` | 2 | 135 | | 0% coverage |
| `dashboard/` | 2 | 119 | | 0% coverage |

All counts `inv`.

### 3.3 Web app (`apps/web`)

| Aspect | State |
|---|---|
| Framework | Next.js 16.2.6 App Router, React 19.2.6, behind a custom `server.mjs` (Next handler plus WebSocket relay at `/api/runtime/relay/*`) |
| Middleware | `src/proxy.ts`: rate limits (120/min per IP, 20/min provider login), cross-site mutation block, session-cookie presence check, page gating to `/login` or `/setup` |
| Pages | 17 page routes, 9 redirect stubs. Main routes: `/`, `/runtime`, `/runtime/[agentId]/tasks/[taskId]`, `/control-plane`, `/control-plane/agents/[agentId]`, `/control-plane/system/*`, `/executions`, `/executions/dlq`, `/sessions`, `/routines/schedules`, `/memory`, `/evaluations`, `/costs`, `/settings/account`, `/login`, `/setup`, `/forgot-password`, `/oauth/callback` |
| BFF route handlers | ~37: `/api/control-plane/[...path]` (catch-all proxy), `/api/control-plane/auth/*`, `/api/runtime/{agents,artifacts,costs}`, `/api/channels/[agentId]`, `/api/elevenlabs/voices`, `/api/health` (`inv` for the tree) |
| Source layout | `src/{app,components,hooks,lib,types,test}`; `lib/contracts/*` zod request-body registry; hand-mirrored TS types (`lib/types.ts`, `lib/squads.ts`, `runtime-types.ts`), no codegen |
| Design system | Tokens in `globals.css` (light `:root`, dark via media query and `html[data-theme=dark]`), primitives in `components/ui`; ends with a global `box-shadow: none !important` reset; `apps/web/CLAUDE.md` has drifted from code (accent, button heights, shadow tokens, test paths) |
| i18n | 5 locales, ~32k lines of resources, key-parity contract test, module-level language state; server-rendered text is always en-US |
| Tests | vitest + jsdom (157 files, serial: `fileParallelism` off, `maxWorkers` 1); test files excluded from `tsconfig`, 52 type errors in 21 test files (`run`); Playwright suite in `tests/e2e` not in CI |
| Dead code | 71 files (~12k lines) unreachable from any route or proxy entry (`run`, import-graph script); `lib/runtime-dashboard.ts` (897 lines) plus 8 `/api/runtime/*` GET routes have no caller |

### 3.4 npm CLI (`packages/cli`)

| Aspect | State |
|---|---|
| Package | `@openkodaai/koda` 1.0.18, Node `>=20`, zero dependencies, `bin/koda.mjs` (`inv`) |
| Commands | `install`, `up`, `down`, `doctor`, `update`, `logs`, `uninstall`, `auth` |
| Release payload | `release/manifest.json`, `CHECKSUMS.txt`, `bundle/{docker-compose.release.yml, proxy/nginx.conf, MIGRATION.md, sbom.spdx.json}` (`inv`) |
| Install target | `~/.koda`, `.env.bootstrap` with generated secrets, GHCR images |
| Known state | `uninstall` without `--purge` deleted all volumes; fixed at `7b848cf` (`run`, VALIDATION_REPORT). `update` rollback restores code only. SBOM is a stub. Manifest references mutable image tags, not digests. |

### 3.5 Rust workspace (`rust/`)

| Crate | Kind | Purpose | Deployed as | Notes |
|---|---|---|---|---|
| `koda-proto` | lib | tonic/prost generated types | linked | |
| `koda-observability` | lib | `tracing` setup | linked | |
| `koda-postgres` | lib | bb8 + tokio-postgres pool | linked | policy-engine bypasses it |
| `koda-security-core` | lib | Shell and path validation, env sanitisation (regex) | linked by runtime-kernel, artifact, security-service | third copy of the shell blocklist |
| `koda-security-service` | bin | gRPC wrapper over `koda-security-core` | `security` container (default) | network hop for pure functions; hard dependency for shell and redaction |
| `koda-runtime-kernel` | bin | Process supervisor: agent workers, task environments, terminals, browser, checkpoints | `runtime-kernel` container, built on the full Python image | only sidecar whose separation is clearly earned; in-memory state not reconciled with `runtime_*` tables |
| `koda-memory-engine` | bin | Memory recall, curation, projections | `memory` container | second `napkin_log` writer; `Deduplicate` RPC is a no-op |
| `koda-retrieval-engine` | bin | Knowledge retrieval (lexical, dense, graph) | `retrieval` container | well tested; its tables have no producer in primary mode |
| `koda-artifact-engine` | bin | Artifact blobs (S3 or Postgres) | `artifact` container | runs DDL with an exclusive lock on every request |
| `koda-policy-engine` | bin | Quotas | profile `policy-engine` | no operator configuration entry point |
| `koda-bot-gateway` | bin | Telegram long polling | profile `bot-gateway` | claims at-least-once delivery but acks failed updates |
| `koda-command-guard` | cdylib (PyO3, excluded from workspace) | Linear-time shell blocklist for Python | not shipped in any image; built only in `benchmarks.yml` | own `Cargo.lock`, skipped by cargo-audit and Dependabot |

Workspace membership `inv`. No `rust-toolchain.toml` (`inv`).

### 3.6 Protobuf contracts (`proto/`)

| Package | Python client | Consumer status |
|---|---|---|
| `security/v1` | `internal_rpc/security_guard.py` (sync) | default, required |
| `runtime/v1` | `internal_rpc/runtime_kernel.py` | default, required |
| `memory/v1` | `internal_rpc/memory_engine.py` | default |
| `retrieval/v1` | `internal_rpc/retrieval_engine.py` (sync) | default |
| `artifact/v1` | `internal_rpc/artifact_engine.py` | default; artifact ingestion hard-fails without it |
| `policy_engine/v1` | `internal_rpc/policy_engine.py` | opt-in, not configurable |
| `bot_gateway/v1` | `internal_rpc/bot_gateway.py` | opt-in |
| `common/v1` | shared types | |

Codegen: `scripts/internal_rpc_codegen.sh` (buf) for Python into `koda/internal_rpc/generated/`; Rust via
`tonic-build` with vendored `protoc`. Codegen is manual; CI has no drift or breaking-change check.

### 3.7 Entry points

| Entry point | Invocation | What runs |
|---|---|---|
| `koda`, `koda-control-plane` console scripts | `koda.control_plane.__main__:main` | Supervisor process: aiohttp control plane on `:8090`, reconcile loop, `RuntimeKernelLink` gRPC to the kernel, `/health` and `/cluster/*` |
| `launcher.py` | `python launcher.py` | Same supervisor (`run_supervisor()`) |
| `koda-runtime-worker` console script | `koda.__main__:main` | One agent worker: PTB application, queue workers, health and runtime API server, scheduler dispatcher, MCP bootstrap. Normally spawned by the runtime-kernel via `EnsureAgentWorkers`. A direct `python -m koda --agent-id` launch reads config before control-plane env hydration (support status unknown). |
| `python -m koda migrate` | `koda/cli/migrate.py` | Applies schema migrations (also applied on boot) |
| `apps/web/server.mjs` | `pnpm dev:web`, `node server.mjs` | Next.js server plus WS relay |
| `packages/cli/bin/koda.mjs` | `npx @openkodaai/koda` | Release installer |
| Rust binaries (7) | sidecar containers | gRPC services listed in 3.5 |
| `scripts/install.sh` | shell | Source install helper |
| `koda.service.example` | systemd | `docker compose up -d` |

### 3.8 Build and developer scripts

Root `package.json` scripts: `dev:web`, `dev:stack` (and `:build`, `:down`, `:logs`), `release:check-metadata`,
`release:sync-metadata`, `release:build-artifacts`, `build:release:bundle`, `lint:web`, `test:web`, `test:web:ci`,
`build:web`. `apps/web` adds `test:e2e`, `test:e2e:ui`, `test:e2e:report`.

| Group | Scripts (`scripts/`) | Notes |
|---|---|---|
| Release | `build_release_artifacts.py`, `build_release_bundle.py`, `release_metadata.py`, `release_smoke_test.py`, `npm_registry_metadata.py`, `sync_npm_readme.py` | |
| Install and ops | `install.sh`, `doctor.py`, `generate_env_secrets.py`, `docker_smoke.sh`, `cluster_smoke.sh` | `generate_env_secrets.py` added at `3f895ee` |
| Data migrations | `migrate_execution_policies.py`, `migrate_object_storage.py`, `migrate_variable_scopes.py` | object-storage script is a legacy MinIO migration |
| Seeds | `seed_demo_data.py`, `seed_e2e_data.py` | |
| Smokes, evals, benchmarks | `channel_gateway_smoke.py`, `squad_smoke.py`, `eval_smoke.py`, `live_gate_smoke.py`, `ops_benchmark.py` | `live_gate_smoke.py` only checks env vars |
| CI helpers | `check_pr_quality.sh`, `convert_bandit_json_to_sarif.py`, `review_dependency_changes.py` | |
| Codegen | `internal_rpc_codegen.sh` | |
| Docs | `capture_docs_screenshots.py` | |
| `scripts/dev/` | `build_command_guard.sh`, `dev-restart.sh`, `run_control_plane_dev.py`, `run_web_dev.sh` | `dev-up.sh` / `dev-down.sh` for the local-native path do not exist here (`inv`) |
| `scripts/git-hooks/` | git hooks | |

Python packaging: setuptools via `pyproject.toml`, locked by `uv.lock` (uv 0.10.7 in images). Images install from
`uv export`, then `pip install --no-deps .`.

### 3.9 Configuration

| Item | State |
|---|---|
| `koda/config.py` | Central env-driven settings (~381-387), prompt composition, namespaced paths, placeholder-secret detection (`is_placeholder_secret`, `_env_secret`, added at `3f895ee`). Loads `.env` at import time. |
| Parallel config modules | `control_plane/settings.py` (own dotenv load), `services/cache_config.py`, `services/confidence_config.py`, `memory/config.py`, `knowledge/config.py`. `cache_config.py` and `confidence_config.py` diverge from `config.py`. |
| Published agent config | Control plane publishes `AgentSpec` into `cp_agent_config_versions` snapshots that embed secret ciphertext; workers hydrate env from the snapshot. Secret changes need a republish. This is why the env surface is so large. |
| `.env.example` | 17 KB template; placeholders are now rejected at runtime |
| Documentation coverage | ~191 of ~606 repo-wide env vars documented (devops count); 68 documented in `docs/config/reference.md` (product-scope count) |
| Feature flags off by default | `SQUADS_ENABLED`, `RUNTIME_ENVIRONMENTS_ENABLED` (~6k lines behind it); `OBJECT_STORAGE_REQUIRED` defaults to `true` |
| Dead settings | Neo4j settings (including a password variable), `PLUGIN_SANDBOX_ENABLED`, `PLUGIN_DIRS`, `WORKFLOW_MAX_PARALLEL`, `INTER_AGENT_MESSAGE_TIMEOUT`, `ADMIN_USER_IDS` (consumer `is_admin` unused); control-plane exposes some runtime keys nothing consumes |
| Secret material | Fernet master key file on the `koda-state` volume (also reused as HMAC key; no backup tooling; `rotate_master_key` has no production caller); `RUNTIME_LOCAL_UI_TOKEN` (HMAC runtime tokens, 300 s); `WEB_OPERATOR_SESSION_SECRET`; `CONTROL_PLANE_API_TOKEN` (break-glass) |
| Tool config | `pyproject.toml` (ruff, mypy with 13 unused overrides, pytest with 16 markers, coverage `fail_under = 53.5`), `eslint.config.mjs`, `tsconfig.json`, `vitest.config.ts`, `playwright.config.ts`, `next.config.ts`, `postcss.config.mjs`, `.gitleaks.toml`, `.snyk`, `.dockerignore`, `.github/dependabot.yml` |

### 3.10 Schemas and migrations

| Item | State |
|---|---|
| Database | One PostgreSQL 16 + pgvector instance, one schema (`KNOWLEDGE_V2_POSTGRES_SCHEMA`, default `knowledge_v2`) holding all app state: `cp_*` control-plane tables, knowledge, `napkin_log`, squads, `runtime_*`, scheduler, audit, `query_history`, approvals |
| Migration registry | 50 `_Migration` entries in `KnowledgeV2PostgresBackend._migrations()` (`koda/knowledge/v2/postgres_backend.py:536`), tracked in `schema_migrations`; inline SQL, forward-only (`inv`) |
| Application | On boot and via `python -m koda migrate`; `migrations-gate.yml` checks for pending migrations (path-filtered) |
| Integrity | ~130 tables, 7 foreign keys; TEXT timestamps and INTEGER booleans (SQLite leftovers); approval tables store Telegram IDs as INTEGER and are wiped across agents; `agent_id` casing differs (upper in `postgres_backend.py:175`, lower in `agent_scope.py:19`) |
| Out-of-registry DDL | Rust artifact engine creates its own table at request time |
| Cross-language coupling | Rust services read and write Python-owned tables (`napkin_log`, `query_history`, `audit_events`, `cp_telegram_offsets`) through hand-written SQL; a Python migration can break a sidecar at runtime |
| Known defects | Daily retention purge targets tables that do not exist (`read`); pgvector dimension default 1024 vs the 384-dim default embedding model (`read`, latent) |
| Legacy storage | 29 dead SQLite branches in `state/history_store.py`; JSON fallbacks in `STATE_ROOT_DIR` (`pending_approvals.json`, `approval_grants.json`) |
| API schema | `docs/openapi/control-plane.json` (OpenAPI 3.1, v1.0.18, served at `/openapi/control-plane.json`): paths match code; 217 of 304 operations have generic responses; security markings are wrong |
| Web contracts | zod schemas in `apps/web/src/lib/contracts`, hand-mirrored; schedule schemas use `passthrough()`, so non-contract fields reach the backend unchecked |
| RPC contracts | `proto/*/v1` (section 3.6) |

### 3.11 Infrastructure and deployment

Images (`inv` for bases):

| Dockerfile | Build stage(s) | Runtime base | Produces | Notes |
|---|---|---|---|---|
| `Dockerfile` | `node:26-slim` (provider CLIs) | `python:3.12-slim` | `app` (supervisor, control plane) | provider CLIs installed with `npm install -g` and no version (lines 5-8); extra unlocked `pip install playwright` (line 86); Chromium, xvfb/x11vnc, ffmpeg, espeak; ~6 GB |
| `Dockerfile.runtime-kernel` | `node:26-slim`, `rust:1.95-slim` | `python:3.12-slim` | `runtime-kernel` and all agent workers | duplicates the `app` stack (~6 GB) |
| `Dockerfile.{security,memory,retrieval,artifact}` | `rust:1.95-slim` | `debian:13.4-slim` | Rust sidecars | each compiles the full workspace; `apt-get install protobuf-compiler` is redundant (protoc vendored) |
| `Dockerfile.{bot-gateway,policy-engine}` | `rust:1.95-slim` | `debian:bookworm-slim` | opt-in sidecars | glibc mismatch if `rust:1.95-slim` is trixie-based (`unverified`, needs a Docker build) |
| `apps/web/Dockerfile` | `node:26-slim` (4 stages) | `node:26-slim` | `web` | |
| `apps/web/Dockerfile.dev` | | `node:26.1.0-trixie-slim` | dev web | |

Compose files:

| File | Purpose | CI coverage | State |
|---|---|---|---|
| `docker-compose.yml` | Base stack: 10 default services, profiles `policy-engine` and `bot-gateway`; networks `frontend`, `backend`; volumes `koda-state`, `koda-runtime`, `koda-artifacts`, `postgres-data`, `seaweedfs-data`, `tmp-images` | `docker-smoke` (curl only) | `app` publishes `${CONTROL_PLANE_PORT:-8090}` on all interfaces (`inv`) |
| `docker-compose.dev.yml` | Dev overrides for `app`, `web`, `runtime-kernel` | none | |
| `docker-compose.prod.yml` | Loopback port bindings, `restart: always` | none | broken: ports are appended, not replaced (`run`) |
| `docker-compose-cluster.yml` | Replicated `app`, `memory`, `retrieval` | none | broken: every replica gets the same supervisor ID (`run`) |
| `docker-compose-observability.yml` | Prometheus 2.55.0, Grafana 11.3.0, Tempo 2.6.1, postgres-exporter 0.16.0 | none | broken: scrapes a `/metrics` the control plane does not serve; only Postgres metrics flow (`run`) |
| `packages/cli/release/bundle/docker-compose.release.yml` | Release stack from GHCR (same 10 services) | release smoke | hand-maintained copy of the base file; has drifted |

Default services:

| Service | Image / build | Role | Exposure |
|---|---|---|---|
| `app` | `Dockerfile` | Supervisor and control-plane API (`:8090`), reconcile loop; spawns MCP servers ad hoc for test/verify/discover | host-published on all interfaces in the base file; backend auth is the real boundary |
| `web` | `apps/web/Dockerfile` | Next.js console (`:3000`), read-only root fs | host-published; on both `frontend` and `backend` networks |
| `runtime-kernel` | `Dockerfile.runtime-kernel` | Rust supervisor; agent workers run as its children | workers bind `/health` and `/metrics` to `127.0.0.1` inside the container, so nothing outside can scrape them |
| `security`, `memory`, `retrieval`, `artifact` | Rust Dockerfiles | gRPC sidecars | `backend` network; no RPC authentication |
| `postgres` | `pgvector/pgvector:pg16` | All durable state | |
| `seaweedfs` | `chrislusf/seaweedfs:4.05` | Bundled S3 store (`:8333`) | |
| `seaweedfs-init` | `amazon/aws-cli:2.27.41` | Bucket bootstrap job | |
| `policy-engine`, `bot-gateway` | Rust Dockerfiles | Opt-in profiles | |

Other operational assets: `docs/operations/{prometheus.yml, alerts.yml, tempo.yaml, grafana/}`, release `proxy/nginx.conf`,
`koda.service.example`. The backup runbook depends on `weed s3 sync`, whose validity for SeaweedFS 4.05 is `unverified`.

### 3.12 CI/CD (`.github/workflows`)

| Workflow | Lines | Trigger | Jobs | Notes |
|---|---:|---|---|---|
| `pr-quality.yml` | 304 | PR, push, dispatch | `workflow-quality` (actionlint), `python-quality`, `python-tests` (3.11, 3.12, macOS), `python-postgres-tests`, `web-quality`, `auto-sync-npm-readme`, `repo-hygiene`, `rust-quality`, `docker-smoke` | Postgres job added at `30a7fe5`, not yet run; web job has no `tsc` over tests and no e2e; smoke only curls |
| `security.yml` | 337 | PR, push, schedule, dispatch | `dependency-review`, `dependency-audit` (pip-audit, pnpm audit, cargo-audit), `sast` (bandit high-only `-lll -iii`, gitleaks), `codeql`, `container-scan` (Trivy) | Trivy skips the bot-gateway and policy-engine images |
| `snyk.yml` | 168 | PR, push, schedule, dispatch | `open-source` | exports from the uv env; overlaps pip-audit and pnpm audit |
| `release.yml` | 1,214 | push, dispatch | re-runs PR and security jobs, then `build-release-bundle`, `npm-pack-smoke`, `ensure-release-tag`, `publish-ghcr` (buildx multi-arch, provenance and SBOM attestations), `publish-npm`, `npm-public-install-smoke`, `github-release` | duplicates `pr-quality.yml` and `security.yml` |
| `cut-release-tag.yml` | 392 | push, dispatch | `cut-release-tag` | |
| `benchmarks.yml` | 51 | PR (path-filtered) | `bench` | builds `koda-command-guard` with maturin; installs without the lock |
| `migrations-gate.yml` | 64 | PR (path-filtered) | `check-pending-migrations` | installs without the lock |
| `ci.yml` | 17 | dispatch | `legacy-ci-transition` | dead stub |

Supply-chain facts (`inv`): actions are pinned to tags, not SHAs, and several float on major or channel tags
(`astral-sh/setup-uv@v7`, `docker/*@v3`, `dtolnay/rust-toolchain@stable`, `softprops/action-gh-release@v2`,
`actions/download-artifact@v4`). CI uses Node 22 while images ship Node 26. Dependabot covers actions, pip, npm,
docker (`/`, `/apps/web`) and cargo (`/rust` only). Whether its pip ecosystem updates `uv.lock` is `unverified`.
Which checks are required by branch protection is unknown.

### 3.13 Tests

| Layer | Location | Size | In CI | Notes |
|---|---|---|---|---|
| pytest (default) | `tests/` | 326 `test_*.py` files (`inv`); ~4,256 functions; 5,074 collected; 4,897 passed, 200 skipped at HEAD | yes | `conftest.py` forces `STATE_BACKEND=postgres` with no DB, sets execution approval to `True` globally (this hides the approval-contextvar defect), and auto-starts the real Rust security guard. 212 of 324 files use mock or monkeypatch (2,145 `patch(` calls). Only 4 of 109 dispatcher tests hit the real policy gate. |
| pytest `postgres` marker | same | 188 tests; 186 passed, 2 skipped with DSN | new job, not run yet | serial-only (shared-schema TRUNCATE isolation); DSN scoping patches import-time config copies |
| vitest | `apps/web/src` | 157 files, 692 tests | yes | BFF route handlers mostly untested; no coverage provider |
| Playwright | `apps/web/tests/e2e` | 23 tests in 11 files | no | needs the Docker stack; specs mostly assert page text |
| cargo test | `rust/` | ~95 tests | yes | uneven distribution, no coverage tooling; `koda-command-guard` tests never run |

Coverage hot spots (line coverage): `__main__.py` 4%, `state/history_store.py` 25%, `control_plane/api.py` 37%,
`control_plane/manager.py` 50%, `queue_manager.py` 58%, `tool_dispatcher.py` 74%, `operator_auth.py` 83%;
`dashboard`, `runtime`, non-Telegram adapters and `memory/manager` 0%. `_execute_single_task` is always patched out;
the control-plane auth middleware has no test. Sidecars exercised for real from Python: security-service and
bot-gateway only; memory, retrieval, artifact and runtime-kernel are tested against fakes.

Dead test inventory: 11 of 16 declared markers unused; `provider_keys` unused; `tests/e2e` and `tests/eval` empty;
the testcontainers branch in `tests/postgres_fixtures.py:41-78` is dead (package not declared).

### 3.14 Documentation

| Area | Files | Notes |
|---|---|---|
| Root | `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE` (Apache-2.0), `CHANGELOG.md` (foreign) | |
| `docs/architecture/` | 15 | |
| `docs/operations/` | 26 entries (runbooks plus Prometheus, alerts, Tempo, Grafana configs) | |
| `docs/security/` | 9 | `authentication.md` has drifted from code in security-relevant places; it and `cluster-mode.md` describe port 8090 as loopback or internal-only |
| `docs/install/` | `local.md`, `vps.md`, `object-storage-migration.md` | |
| `docs/squads/` | 4 | the flags that enable squads are not documented |
| `docs/reference/` | `api.md`, `releases.md` | |
| `docs/config/reference.md` | env reference | covers a small fraction of settings |
| `docs/openapi/control-plane.json` | OpenAPI 3.1 | see 3.10 |
| `docs/engineering/` | `MISSION.md`, `EXECUTION_STATUS.md`, `QUALITY_BASELINE.md`, `VALIDATION_REPORT.md`, this file | `QUALITY_BASELINE.md` says no Playwright suite exists; 23 tests do |
| `apps/web/AGENTS.md`, `apps/web/CLAUDE.md` | UI design guide | drifted from code (see 3.3) |

Undocumented operator surfaces: the requirement that every agent have a Telegram bot token, 60-66 Telegram commands
(including `/shell`, `/docker`, `/pip`, `/js`), ~130 agent tools, voice, workflows, the 5-locale UI, and most env vars.

### 3.15 Repository hygiene

| Issue | Evidence |
|---|---|
| `main-BwqrdVu3.js` (1.21 MB) and `app-server-manager-signals-BEaGjuc8.js` (408 KB) tracked at the root, added in `437f98f`; specialists identified them as OpenAI Codex desktop (Electron) bundles. Licensing and history purge are open. | `inv` (tracked, size, commit); origin `read` |
| `CHANGELOG.md` is the `@googleworkspace/cli` changelog | `inv` |
| `requirements.txt` mirrors `pyproject.toml`, kept in sync only by `tests/test_open_source_hygiene.py:174`; Snyk already exports from uv | `inv` (contents) |
| `ci.yml` dead stub | `inv` |
| `launcher.py` duplicates the console script | `inv` |
| 13 unused `[[tool.mypy.overrides]]` sections | QUALITY_BASELINE |
| Legacy MinIO migration script and references | `read` |
| Local artifacts `.coverage`, `apps/web/playwright-report`, `koda.egg-info`, `rust/target` are gitignored and untracked | `inv` |

## 4. Runtime topology

```
Browser
  -> web (Next.js, server.mjs :3000) -- proxy.ts: rate limit, cross-site block, session cookie
       /api/control-plane/[...path] --Bearer--> app :8090 (supervisor process)
                                                  api.py -> ControlPlaneManager -> state stores
                                                  -> run_coro_sync -> asyncpg -> Postgres
                                                  reconcile loop --gRPC EnsureAgentWorkers--> runtime-kernel
       /api/runtime/agents/* --runtime token--> agent worker runtime API
       /api/runtime/relay/* (WebSocket) ------> worker terminal / browser
       /api/channels/* --decrypted secrets----> third-party channel APIs

runtime-kernel container
  one Python worker per agent (koda.__main__)
    PTB long polling <- Telegram
    queue_manager -> provider CLIs (subprocess) / HTTP LLM APIs
    scheduler dispatcher, MCP servers (stdio / HTTP)
    /health, /metrics, /api/runtime on 127.0.0.1
    gRPC -> security, memory, retrieval, artifact (+ policy-engine, bot-gateway when enabled)

memory, retrieval, artifact, policy-engine, bot-gateway -> same Postgres schema
artifact -> SeaweedFS (S3)
```

Consequences of this process model (`read`):

- Each worker holds module-global state (queues, locks, task registry, MCP closures) for exactly one agent.
- The dashboard approval routes run in the supervisor and read supervisor memory, not the worker's, so dashboard
  approvals cannot reach a worker.
- Control-plane memory curation cannot invalidate a worker's per-process recall cache.
- Most stores are synchronous over `run_coro_sync`, which blocks the calling event loop for up to 30 s per call, in
  both the supervisor and the workers.
- Telegram is structural: publish fails without `AGENT_TOKEN` and the worker refuses to start, so a dashboard-only
  agent is not possible today.

## 5. Technology and dependency audit

### 5.1 Classification key

| Column | Values |
|---|---|
| Necessity | **Core**: product does not run without it. **Feature**: one feature needs it. **Optional**: guarded import or extra. **Unused**: no live consumer. **Pin**: declared only to floor a transitive version. |
| Redundancy | Overlap with another dependency or with in-house code; `-` if none found |
| Maint | Cost to keep it correct here: L / M / H |
| Upgrade | Risk that a routine upgrade breaks behaviour: L / M / H |
| Disposition | Proposed: **Keep**, **Fix use**, **Consolidate**, **Remove**, **Decide** (blocked on a scope decision, section 9) |

"Modules" is the number of `koda/` modules importing the package directly (`inv`, excludes generated code).

### 5.2 Python runtime dependencies (`pyproject.toml [project.dependencies]`)

| Dependency | Constraint | Modules | Necessity | Redundancy | Maint | Upgrade | Disposition and notes |
|---|---|---:|---|---|---|---|---|
| python-telegram-bot[job-queue] | >=22.7,<23 | 29 | Core | Rust bot-gateway (opt-in) | M | M | Keep. Structural: every worker is a PTB app. Sequential update processing plus lock-holding handlers stalls the whole bot. Auth is per-handler with no central filter. |
| aiohttp | >=3.13.5,<4 | 17 | Core | urllib in Ollama, provider auth, MCP client, OAuth, model downloads; `requests` | L | L | Keep, Consolidate: make it the single HTTP stack. `client_max_size` left at the 1 MiB default. |
| asyncpg | >=0.31,<1 | 15 | Core | 10+ separate pool sites in squads, plus per-service Rust pools | M | L | Fix use: wrapped in a sync bridge that blocks the loop and gives no transactions; per-call `set_type_codec`. |
| grpcio | >=1.80,<2 | 2 (+generated) | Core while sidecars exist | - | M | M | Keep for now; shrinks if sidecars are folded in. Sync clients called from async paths block the loop. |
| protobuf | >=7.34.1,<8 | 1 (+generated) | Core with grpcio | - | L | M | Keep. |
| cryptography | >=48,<49 | 1 | Core | - | L | L | Keep. Fernet at rest; master key reused as HMAC key; three duplicate decrypt helpers. |
| argon2-cffi | >=25.1,<26 | 1 | Core | - | L | L | Keep. Argon2id operator password hashing. |
| structlog | >=25.5,<26 | 1 | Core | - | L | L | Keep. Redacting the `code` key also hides the bootstrap code the docs say is logged. |
| prometheus_client | >=0.25,<1 | 2 | Core | - | L | L | Fix use: 105 metrics but only served on worker loopback; `health.py` imports `generate_latest` unconditionally despite the no-op fallback; `CLAUDE_EXECUTION` metric used for every provider. |
| python-dotenv | >=1.2.2,<2 | 2 | Core | two load points (`config.py`, `control_plane/settings.py`) | L | L | Consolidate: one load point; import-time side effect drives import-order coupling. |
| aiolimiter | >=1.2.1,<2 | 2 | Feature (rate limits) | hand-rolled tool rate limiter in `tool_dispatcher` | L | L | Fix use: control-plane buckets are keyed on client-supplied `X-Forwarded-For` (`read`). |
| croniter | >=6.2.2,<7 | 1 | Feature (scheduler) | - | L | L | Keep. |
| pybreaker | >=1.4.1,<2 | 1 | Feature (resilience) | provider fallback chain, tenacity | M | L | Fix use or replace: check-then-skip pattern never reaches half-open, so open breakers never recover (`run`). |
| tenacity | >=9.1.4,<10 | 1 | Feature (retry on `run_claude` only) | fallback chain, pybreaker | L | L | Remove: hidden second retry layer with one consumer. |
| playwright | >=1.59,<2 | 1 | Feature (browser tools, runtime smoke prerequisite) | - | M | M | Keep. Images also run an unlocked `pip install playwright`. SSRF route guard only active during navigate/download. |
| beautifulsoup4 | >=4.14.3,<5 | 3 | Feature (link analysis, fetch) | - | L | L | Keep. |
| boto3 | >=1.43.6,<2 | 1 | Feature (S3 knowledge payload copies) | Rust `aws-sdk-s3` in artifact engine | M | L | Consolidate with the artifact path. |
| asyncssh | >=2.23,<3 | 1 | Unused (DBManager SSH tunnels started at boot, no tool or handler calls DBManager) | MCP Postgres servers | M | L | Decide: remove with DBManager unless DB tools are revived. |
| PyYAML | >=6.0.3,<7 | 4 | Feature (plugin and skill manifests) | - | L | L | Keep; `safe_load` used. |
| pillow | >=12.2,<13 | 3 | Feature (profile photos, images) | - | L | L | Keep. |
| pypdf | >=6.11,<7 | 1 | Feature (artifact extraction) | - | L | L | Keep. |
| openpyxl | >=3.1.5,<4 | 1 | Feature (artifact extraction) | - | L | L | Keep. |
| python-docx | >=1.2,<2 | 1 | Feature (artifact extraction) | - | L | L | Keep. |
| rapidocr-onnxruntime | >=1.4.4,<2; py<3.13 | 1 | Optional (OCR) | - | M | H | Decide: not installable on 3.13+, so OCR silently degrades (the dev venv is 3.13). |
| kokoro-onnx | >=0.5,<1; py<3.14 | 1 | Feature (local TTS) | supertonic, ElevenLabs | H | H | Decide: pins images to Python 3.12; model check is an 8-hex sha256 prefix. |
| supertonic | >=1.3.1,<2; py<3.14 | 1 | Feature (second local TTS) | kokoro-onnx | M | H | Decide: two local TTS engines. |
| soundfile | >=0.13.1,<1 | 1 | Feature (voice I/O) | - | L | L | Keep with voice. |
| huggingface-hub | >=1.14,<2 | 2 | Feature (model downloads) | urllib downloads for Kokoro and Whisper | L | M | Consolidate downloads behind one verified path; Whisper downloads have no integrity check. |
| requests | >=2.34,<3 | 0 | Pin (no direct import in `koda/`, `scripts/` or `tests/`) | aiohttp, urllib | L | L | Remove from direct deps or comment it as a security floor (`inv`). |
| idna | >=3.15,<4 | 0 | Pin | - | L | L | Keep as security floor; add a comment. |
| lxml | >=6.1,<7 | 0 | Pin (CVE-2026-41066 floor, commented) | - | L | L | Keep. |
| urllib3 | >=2.7,<3 | 0 | Pin | - | L | L | Keep as security floor; add a comment. |

### 5.3 Python optional, undeclared and dev dependencies

| Dependency | Declared | Modules | Necessity | Notes | Disposition |
|---|---|---:|---|---|---|
| pywa, discord.py, slack-bolt[async], line-bot-sdk | extras `whatsapp`, `discord`, `slack`, `line`, `channels-all`; `teams = []` is empty | 1 each | Unused | only consumers are unwired adapters | Decide (remove with adapters) |
| sentence-transformers | no (absent from `uv.lock`, `inv`) | 4 | Optional | knowledge query embeddings, squad semantic routing, skill selection, script library, semantic cache. The app `Dockerfile` has an explicit "not installed in this image" branch (`inv`). Squad router refuses lexical fallback while the skill index falls back to hash vectors. End-to-end effect in shipped images is `unverified`. | Decide (declare as an extra or drop consumers) |
| faiss-cpu | no | 1 | Optional | `SEMANTIC_CACHE_BACKEND=vector`; one of three cache-lookup strategies | Remove unless an eval justifies it |
| opentelemetry-* | no (absent from `uv.lock`) | 3 | Optional | tracing is always a no-op in shipped images; one span; gRPC propagation helpers unused | Decide |
| cross-encoder reranker (`services/reranker.py`) | via sentence-transformers | | Optional | memory recall behind a flag; runs synchronously on the event loop | Decide |
| yt-dlp, ffmpeg, espeak, Chromium | system binaries | | Feature | yt-dlp is undeclared; others baked into images | document |
| testcontainers | no | tests only | Unused | dead fixture branch | Remove |
| Dev: pytest, pytest-asyncio, pytest-cov, hypothesis, ruff, mypy, types-PyYAML, pygments, pip-audit, bandit, watchfiles | `[project.optional-dependencies].dev` and `[dependency-groups].dev` (duplicated lists) | | Dev | hypothesis used in one file; no `--strict-markers`; `-v` in addopts | Consolidate the two dev lists |

### 5.4 Web dependencies (`apps/web/package.json`)

| Package | Version | Necessity | Redundancy | Maint | Upgrade | Disposition and notes |
|---|---|---|---|---|---|---|
| next | 16.2.6 | Core | - | M | M | Keep. Custom `server.mjs` rules out serverless and limits concurrent SSE on HTTP/1.1; root layout relies on an `x-koda-pathname` header that Next 16 can drop. |
| react, react-dom | 19.2.6 | Core | - | L | L | Keep. |
| typescript | ^6 | Core (dev) | - | L | M | Keep; very new major. |
| tailwindcss, @tailwindcss/postcss | ^4 | Core | 10.5k-line `globals.css`; unlayered overrides beat utilities | M | M | Fix use. |
| tw-animate-css | ^1.4.0 | Feature | framer-motion | L | L | Consolidate animation approach. |
| @radix-ui/* (avatar, dialog, popover, select, separator, slot, tooltip) | ^1.x / ^2.x | Core | hand-rolled language and agent switcher menus | L | L | Keep; use for the hand-rolled menus. Separator and avatar have near-zero use. |
| class-variance-authority, clsx, tailwind-merge | 0.7.1 / 2.1.1 / 3.6.0 | Core | - | L | L | Keep; CVA used by 5 files. |
| lucide-react | ^1.14.0 | Core | - | L | L | Keep; 166 importers. |
| framer-motion | ^12.38.0 | Feature | tw-animate-css | M | M | Consolidate; 43 files, beyond the guide's CSS-first rule. |
| @tanstack/react-query | ^5.100.10 | Core | hand-rolled `useEffect`/fetch in several screens, stabilising hooks, home-grown fetch-state hook | M | L | Consolidate: three cache policies, two hook conventions. |
| zod | ^4.4.3 | Core | - | M | L | Keep; 42 importers. Contracts hand-synced with Python routes. |
| i18next, react-i18next | ^26.1.0 / ^17.0.7 | Core | custom literal and term-replacement layer, hashed generated keys | H | M | Fix use; Decide on 5 locales. |
| three, @react-three/fiber, @react-three/drei (+@types/three) | ^0.184 / ^9.6.1 / ^10.7.7 | Feature (decorative orb, one consumer) | CSS/SVG glyph | M | H | Decide; strong removal candidate. |
| recharts | ^3.8.1 | Feature (costs, dashboard) | - | L | M | Keep; demo-style wrappers. |
| d3-force | ^3.0.0 | Feature (memory graph) | - | L | L | Keep. |
| @xterm/xterm + 5 addons | ^6.0.0 and others | Feature (runtime terminal) | - | L | M | Keep. |
| @novnc/novnc | ^1.7.0 | Feature (remote browser) | - | L | M | Keep. |
| ws | ^8.20.1 | Feature (WS relay in `server.mjs`) | - | L | L | Keep while the custom server exists. |
| date-fns | ^4.1.0 | Feature (recurrence, date picker) | - | L | L | Keep; routine timezone math needs zone-aware helpers (no date-fns-tz). |
| react-markdown, remark-gfm, remark-breaks | ^10.1 / ^4.0.1 / ^4.0 | Feature (markdown rendering) | - | L | L | Not reviewed by specialists. |
| fast-deep-equal, server-only | ^3.1.3 / ^0.0.1 | Utility | - | L | L | Not reviewed by specialists. |
| next/font (Inter, Fraunces, JetBrains Mono) | bundled | Core | - | L | L | Trim: Fraunces serves one heading; Inter loads 5 weights. Build needs Google Fonts network access. |
| Dev: eslint ^9, eslint-config-next 16.2.6, vitest ^4.1.6, vite ^8, jsdom ^29.1.1, @testing-library/{react,jest-dom,user-event}, @playwright/test ^1.57, @types/* | | Dev | - | L | M | Keep; wire Playwright into CI; type-check test files. |

Root `package.json` carries 8 `pnpm.overrides` security floors (`inv`).

### 5.5 Rust dependencies

| Dependency | Version | Used by | Necessity | Notes |
|---|---|---|---|---|
| tokio, tokio-stream | 1.52 / 0.1 | all binaries | Core | Keep. |
| tonic, tonic-build, prost, prost-types | 0.12 / 0.12 / 0.13 / 0.13 | all gRPC crates | Core while sidecars exist | pre-1.0; minor bumps are breaking (M upgrade risk). |
| protoc-bin-vendored | 3.1 | build | Core | makes `apt-get install protobuf-compiler` in 7 Dockerfiles redundant. |
| tokio-postgres, bb8, bb8-postgres | 0.7 / 0.8 / 0.8 | koda-postgres; memory, retrieval, artifact, bot-gateway; policy-engine directly | Core | policy-engine bypasses the shared pool. |
| aws-config, aws-sdk-s3, aws-credential-types | 1.x | artifact engine | Feature | duplicates Python boto3. |
| reqwest (rustls) | 0.12 | bot-gateway | Optional | only if bot-gateway stays. |
| regex | 1.11 | security-core, command-guard | Core | |
| pyo3 | 0.24.1 (abi3-py311) | command-guard | Unused in shipped images | Remove with the crate. |
| serde, serde_json, sha2 (0.11), libc, uuid (1.13), anyhow, thiserror, async-trait, async-stream, futures, tracing, tracing-subscriber | workspace | various | Utility | `uuid` only in policy-engine; retrieval and runtime-kernel pin serde outside the workspace table. |

### 5.6 Toolchains, base images and infrastructure services

| Component | Version | Notes | Upgrade risk |
|---|---|---|---|
| Python | `>=3.11` declared; 3.12 in images; 3.11 and 3.12 in CI; 3.13 local venv | 3.12 pinned by kokoro-onnx and rapidocr constraints | M |
| uv / pip | uv 0.10.7, pip 26.0 in images | lockfile drives images; benchmarks and migrations-gate install without it | L |
| Node.js | `node:26-slim` images; Node 22 in CI; CLI `>=20` | tested on 22, shipped on 26 | M |
| pnpm | 10.26.2 | | L |
| Rust | `rust:1.95-slim` in Docker; `stable` in CI; no `rust-toolchain.toml` | unpinned CI toolchain | M |
| Runtime bases | `debian:13.4-slim` (4 sidecars) vs `debian:bookworm-slim` (bot-gateway, policy-engine) | glibc mismatch `unverified` | M |
| Provider CLIs | `@anthropic-ai/claude-code`, `@openai/codex`, `@google/gemini-cli`, unpinned | non-reproducible builds; upstream compromise flows into images; adapters parse CLI help text and JSON events | H |
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | | L |
| SeaweedFS + aws-cli init | 4.05 / 2.27.41 | 2 containers for bundled S3 | L |
| Observability overlay | Prometheus 2.55.0, Grafana 11.3.0, Tempo 2.6.1, postgres-exporter 0.16.0 | non-functional for Koda metrics and traces | L |

### 5.7 CI, security and release tooling

| Tool | Where | Necessity | Redundancy | Notes |
|---|---|---|---|---|
| actionlint, ruff, mypy, pytest, vitest, eslint, cargo fmt/clippy/test | `pr-quality.yml` | Core | re-run in `release.yml` | |
| pip-audit, pnpm audit, cargo-audit | `security.yml` | Core | Snyk, dependency-review, `review_dependency_changes.py` | three SCA layers for Python and Node; cargo-audit skips command-guard's lockfile |
| Snyk | `snyk.yml` | Optional | pip-audit, pnpm audit | |
| bandit | `security.yml` | Core | CodeQL | high-severity and high-confidence only |
| gitleaks | 8.30.1 | Core | - | |
| CodeQL | v4 | Core | bandit | |
| Trivy | 0.69.3 | Core | - | skips 2 opt-in images |
| Dependabot | `.github/dependabot.yml` | Core | - | skips command-guard; pip vs uv lock `unverified` |
| buf | `v1beta1` config | Feature | - | manual, deprecated format |
| maturin | benchmarks only | Unused in shipping | - | Remove with command-guard |
| GHCR buildx multi-arch | `release.yml` | Core | - | 7 images with provenance and SBOM attestations; release manifest uses mutable tags |

### 5.8 Redundancy clusters

| Area | Parallel implementations | Evidence |
|---|---|---|
| HTTP clients | aiohttp; urllib (Ollama, provider auth, MCP HTTP, MCP OAuth, model downloads); `requests` declared but unused. Different SSRF and redirect semantics; urllib OAuth paths lack private-IP checks. | `read`; `requests` `inv` |
| Retry and resilience | tenacity (`run_claude`), pybreaker (`resilience.py`), provider fallback chain; aiolimiter vs hand-rolled tool rate limiter | `read` |
| Shell blocklist | Python guard, Rust `koda-security-core` over gRPC, PyO3 `koda-command-guard` | `read` |
| Execution policy | `koda/services/execution_policy.py` and `koda/control_plane/execution_policy.py` return different decisions for the same validated policy | `run` |
| Tool catalogs | 5 catalogs with measured drift | `run` |
| MCP catalogs and routes | `koda/integrations/mcp_catalog.py` and `koda/control_plane/mcp_catalog.py` (one used only by a test); duplicate `/mcp/connections/*` and `/connections/*` route families; three MCP policy stores | `read` |
| Memory logic | Python and Rust scoring models; two `napkin_log` writers; lexical retrieval in both languages | `read` |
| Object storage | boto3 (Python knowledge) and aws-sdk-s3 (Rust artifact) | `read` |
| Postgres connections | Shared backend pool, 10 separate asyncpg pool or connect sites in squads, one pool per Rust service | `read` |
| LISTEN/NOTIFY | `AgentInboxListener` (reconnects) and `SquadEventHub` (does not) | `read` |
| Semantic cache | three lookup strategies | `read` |
| Local TTS | kokoro-onnx and supertonic (plus ElevenLabs remote) | `read` |
| Contract layers | `AgentTurn` and `RunGraph` versioned contracts used only for audit; provider metadata spread across ~7 modules | `read` |
| Squad routing | pipeline duplicated between `squad_handlers.py` and `control_plane/api.py` | `read` |
| Config | `config.py`, `control_plane/settings.py`, `cache_config.py`, `confidence_config.py` | `read` |
| Dashboard aggregation | Python `dashboard_service.py` and Node `lib/runtime-dashboard.ts` plus 8 GET routes (no caller) | `read` |
| Web UI primitives | two button systems, two error-state components, nav metadata in 3 places, 7+ fetch helpers, 4 SSE reconnect loops, 3+ error parsers, 3 cache policies | `read` |
| Distribution | source vs release compose files; app vs runtime-kernel images (~6 GB each); 6 near-identical Rust Dockerfiles; `pyproject.toml` vs `requirements.txt`; duplicated dev dependency lists | `inv` / `read` |
| CI | `release.yml` re-implements `pr-quality.yml` and `security.yml` | `inv` |

## 6. External integrations

### 6.1 LLM providers

| Provider | Transport | Module | Conversation history | Notes |
|---|---|---|---|---|
| Claude Code CLI (`claude`) | subprocess or runtime-kernel | `services/claude_runner.py` | native sessions | runs with `bypassPermissions`; tenacity retry plus pybreaker; CLI login via OAuth relay whose route is unreachable (requires a bearer token) |
| OpenAI Codex CLI (`codex`) | subprocess | `services/codex_runner.py` | native sessions | runs with `danger-full-access` |
| Gemini CLI (`gemini`) | subprocess | `services/gemini_runner.py` | none within a session | runs with `yolo` |
| Ollama | HTTP via urllib (blocking, not cancellable) | `services/ollama_runner.py` | none | `host.docker.internal:11434` from the container |
| llama.cpp | HTTP | `services/llamacpp_runner.py` | none | |
| MLX | local process | `services/mlx_runner.py` | none | Apple Silicon only; cannot run in the Linux images |
| OpenAI-compatible cloud APIs: DeepSeek, Groq, Kimi (`api.moonshot.ai`), Mistral, OpenRouter, Perplexity, Qwen (`dashscope-intl.aliyuncs.com`), xAI | aiohttp | `services/openai_compatible_runner.py` (`_PROFILE_BUILDERS`, 8 profiles, `inv`) | none | capability warning claims transcript replay; code does not replay (`read`) |

Internal LLM consumers: memory extraction (default `claude-sonnet-4-6`, dry-run, $0.02 budget per turn), squad
coordinator planner (`semantic_llm`, receives untrusted user text), semantic judge. Provider auth verification runs in
`services/provider_auth.py` over urllib. `api.openai.com` and `api.githubcopilot.com` are also referenced in code;
their call sites were not reviewed. No live provider tests exist.

Security boundary: Koda's policy gate, approvals and shell guard only govern `<agent_cmd>` tool calls. Provider-native
tools run with permissions bypassed, and the runtime kernel adds no OS sandbox (`read`). Whether deployments assume an
external container sandbox is an open question.

### 6.2 Messaging channels

| Channel | Library | State |
|---|---|---|
| Telegram Bot API (`api.telegram.org`) | python-telegram-bot in every worker; optional Rust bot-gateway | Live and mandatory per agent. Forum-topic binding for squads; outbound squad posting calls `get_me` and `get_chat_member` on every dispatch. |
| WhatsApp (`graph.facebook.com`), Discord, Slack, Microsoft Teams, LINE, Messenger, Signal, Instagram | pywa, discord.py, slack-bolt, line-bot-sdk, or none | Adapters exist in `koda/channels`, are never started, and have 0% coverage. The dashboard exposes credential forms; `/api/channels/*` in the web tier fetches decrypted secrets (`include_value=true`) and calls the third-party APIs directly. |
| Webhooks | `channels/webhook_dispatcher.py`, `services/webhook_manager.py` | Webhook and `event_wait` tools are non-functional. |

### 6.3 MCP servers

| Aspect | State |
|---|---|
| Client | Hand-rolled JSON-RPC over stdio and urllib HTTP POST (`services/mcp_client.py`); no `Mcp-Session-Id`, `Accept` header or SSE handling. Compatibility with Streamable HTTP servers is `unverified`. |
| Remote catalog entries (URLs in code, `inv`) | Atlassian, Box, Canva, ClickUp, Cloudflare, Figma, GitHub (`api.githubcopilot.com`), HubSpot, Miro, Notion, PostHog, Postman, Slack, Stripe, Superhuman Mail, Supabase, Vercel, Zapier. Whether any connect is `unverified` (needs credentials). |
| Stdio servers | Launched via `npx` and similar (for example a Postgres MCP server); wrapped by `services/mcp_isolation.py` |
| Isolation | bubblewrap, `sandbox-exec` or Docker selected per host; per-server constraints are stored but never passed in; bwrap does not implement `egress_allowlist`; Docker mode leaves secret env files behind |
| Auth | `services/mcp_oauth.py` (urllib, no private-IP checks); tokens and env values encrypted at rest |
| Policy | `cp_mcp_tool_policies` plus the `mcp_risk` taxonomy |
| Process placement | Workers bootstrap their own servers; the supervisor also spawns servers for test, verify and discover |

### 6.4 Voice, media and models

| Integration | Kind | Notes |
|---|---|---|
| ElevenLabs (`api.elevenlabs.io`) | remote TTS, voice catalog | web route `/api/elevenlabs/voices`; `services/elevenlabs_catalog.py` |
| Kokoro | local ONNX TTS | model downloaded via urllib; 8-hex sha256 prefix check only |
| Supertonic | local ONNX TTS | Hugging Face `snapshot_download` |
| Whisper | local STT | urllib download with no integrity check |
| Hugging Face Hub (`huggingface.co`) | model hosting | also the source of `paraphrase-multilingual-MiniLM-L12-v2` for embeddings (library not installed in images) |
| Playwright Chromium | browser automation | installed in `app` and `runtime-kernel` images |
| yt-dlp, ffmpeg, rapidocr, pypdf, openpyxl, python-docx | artifact extraction and link analysis | yt-dlp undeclared; OCR unavailable on 3.13+ |

The voice feature is undocumented.

### 6.5 Storage and data

| Integration | Notes |
|---|---|
| PostgreSQL + pgvector | single store for all state, knowledge and vectors; shared by Python and 5 Rust services |
| S3-compatible object storage | bundled SeaweedFS by default, or any S3 endpoint (`KNOWLEDGE_V2_S3_*`); Python boto3 and Rust aws-sdk-s3 |
| External Postgres over SSH (asyncssh, DBManager) | pools and tunnels start at boot (`__main__.py:828-839`); no caller. Its read-only guard accepts side-effecting `SELECT` functions (`run`, runtime-scheduling); the tools-mcp review found no tool that reaches it. |
| External databases via MCP | Postgres, Supabase servers |
| Neo4j | configuration only; no code |

### 6.6 Distribution and supply chain

| Integration | Notes |
|---|---|
| GitHub Container Registry | 7 images, multi-arch, provenance and SBOM attestations; release manifest references mutable tags |
| npm registry | `@openkodaai/koda` published with provenance; provider CLIs pulled unpinned at image build |
| GitHub Releases | `release.yml` `github-release` job |
| Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) | required at web build time |
| `cdn.simpleicons.org` | referenced 17 times in code; runtime behaviour not reviewed |
| Snyk, CodeQL | CI services |

### 6.7 Internal service boundaries (gRPC)

| Sidecar | Postgres access | Required by default | Notes |
|---|---|---|---|
| security | none | yes: without it shell commands are blocked and redaction raises | sync gRPC on the event loop for every LLM subprocess env build, shell command and redaction |
| runtime-kernel | none | yes: supervises all workers | in-memory state lost on restart |
| memory | yes | yes | health probed only at client start |
| retrieval | yes | yes | sync client; reads tables with no producer in primary mode |
| artifact | yes, plus S3 | yes for artifact ingestion | DDL under exclusive lock per request |
| policy-engine | yes (own connection) | no (profile) | cannot be configured |
| bot-gateway | yes (`cp_telegram_offsets`) | no (profile) | acks failed updates |

Common to all: no RPC authentication (`x-agent-id` metadata is advisory and agent scope is whatever the caller sends),
partial TLS, UDS or TCP targets configured in `config.py` (~lines 1376-1426) with optional comma-list round-robin. The
`web` container sits on the `backend` network next to these unauthenticated services.

## 7. Dead, unwired and duplicated inventory

| Item | Location | Status |
|---|---|---|
| `startup_validator`, `warm_provider_capabilities`, `is_admin`, legacy tuple queue items, per-user semaphore | `koda/` | dead (`read`) |
| 9 non-Telegram adapters and `ChannelManager` (~1,900 lines) | `koda/channels` | unwired (`read`) |
| DBManager with asyncssh tunnels | `koda/services/db_manager.py` | started at boot, no callers (`read`) |
| Unused sandbox gate; one MCP catalog used only by a test | `koda/services`, `koda/integrations` / `koda/control_plane` | dead (`read`) |
| ~530 lines of legacy import, legacy policy and eval endpoints, duplicate MCP route family | `koda/control_plane` | dead or legacy (`read`) |
| Memory embedding queue and repair loop, no-op Rust `Deduplicate`, namespaces and sensitivity, KnowledgeManager local/OFF path, artifact ingest worker, graph materializer, eval scoring helpers | `koda/memory`, `koda/knowledge`, Rust memory engine | vestigial (`read`) |
| Webhook and `event_wait` tools, snapshot tools, improvement-proposal "apply" (ledger row only), onboarding readiness (hard-coded warnings), audit retention, dashboard aggregator, runtime smoke harness (no entry point) | `koda/services` | unwired or non-functional (`run`/`read`) |
| Route-quality learning, unwired squad persistence code, workflow engine | `koda/squads`, `koda/workflows` | unused (`read`) |
| OTel scaffolding; Neo4j config; dead flags (3.9) | `koda/observability`, `koda/config.py` | dead (`read`) |
| SQLite branches (29), JSON approval fallbacks | `koda/state` | legacy (`read`) |
| `koda-command-guard`, maturin step, native benchmark | `rust/`, `benchmarks.yml` | not shipped (`inv`) |
| `koda-policy-engine` | `rust/` | no operator surface (`read`) |
| 71 unreachable web files (~12k lines), including `components/audit/*`, `components/tasks/*`, dashboard cards, `control-plane/shared/*`, `system/mcp/*`, unused `Badge`/`StatusBadge` | `apps/web/src` | dead (`run`, import-graph script) |
| `lib/runtime-dashboard.ts` and 8 `/api/runtime/*` GET routes; `lib/sse.ts`, `useSSE`, `useAsyncResource`, `useControlPlaneApi`, `usePrefetchRouteData` | `apps/web/src` | no caller (`read`); external consumers `unverified` |
| Generative-UI blocks (~1.8k lines): no backend producer, submit endpoint missing | `apps/web/src` | speculative (`read`) |
| Composer skill and MCP `@mentions` | web composer | silently dropped by backend (`read`) |
| Unused pytest markers (11 of 16), `provider_keys`, empty `tests/e2e` and `tests/eval`, testcontainers branch, env-only live gate | `tests/`, `scripts/` | dead (`read`) |
| `ci.yml` | `.github/workflows` | dead stub (`inv`) |
| Vendor JS bundles, foreign `CHANGELOG.md` | repo root | accidental (`inv`) |

Backend capabilities with no reachable UI (`read`): knowledge-candidate and runbook review, retrieval and answer traces,
squad task claim/complete/escalate and metrics, operator sessions and token management, global defaults, global MCP
catalog, audit log, DLQ retry (Telegram only).

## 8. Discrepancies between sources

| Fact | Reported values | Resolution |
|---|---|---|
| OpenAI-compatible profiles | 10 (core-execution); 8 (product-scope) | 8 entries in `_PROFILE_BUILDERS` (`inv`); Ollama, llama.cpp and MLX are separate runners |
| Control-plane routes | 302 (control-plane, product-scope); 299 (web-features-a) | 302, matched by the OpenAPI parity check (`run`) |
| Settings in `config.py` | 381 (core-execution); ~387 (product-scope) | not reconciled; counting method differs |
| Documented env vars | 191 of 606 repo-wide (devops); 68 (product-scope, `config.py` scope) | different denominators; both kept |
| Telegram commands | ~60 (core-execution); 66 (product-scope) | not reconciled |
| Python test files | 324 (tests-quality); 326 `test_*.py` (`inv`) | `inv` count includes files outside the collected set or added since; not reconciled |
| Rust workspace size | "9 workspace binaries and libraries" (state-rpc) | 11 members plus 1 excluded crate (`inv`) |
| pybreaker scope | only the Claude CLI is protected (core-execution); used by runners, tools, TTS and scheduler (runtime-scheduling) | unresolved |
| DBManager read-only bypass | verified by simulation (runtime-scheduling); no tool reaches DBManager (tools-mcp) | bypass is real in the guard; reachability depends on wiring |
| Placeholder break-glass token in manual installs | open defect (control-plane, devops) | fixed at `3f895ee` (VALIDATION_REPORT, SEC-PLACEHOLDER-SECRETS) |
| `koda uninstall` without `--purge` deletes volumes | open defect (devops) | fixed at `7b848cf` (VALIDATION_REPORT, DATA-UNINSTALL-VOLUMES) |
| Playwright suite | does not exist (QUALITY_BASELINE) | 23 tests in 11 files exist (`run`, listed) |

## 9. Open scope decisions

These decisions gate the "Decide" dispositions above. Each lists the inventory it affects.

| # | Decision | Affects |
|---|---|---|
| 1 | Single-host, single-owner only, or multi-worker and cluster? | lease and janitor machinery, cluster mode, `docker-compose-cluster.yml`, gRPC split |
| 2 | Which sidecars stay out of process (security, memory, retrieval, artifact, policy-engine, bot-gateway)? | 7 Rust binaries, 6 Dockerfiles, grpcio/protobuf, 10-container default stack |
| 3 | Telegram mandatory per agent, and which other channels are in scope? | 9 adapters, 4 optional SDK extras, channel UI, `/api/channels/*` |
| 4 | Squads enabled by default? | `koda/squads`, squad logic in queue_manager and dispatcher, Rooms UI |
| 5 | Runtime environments (`RUNTIME_ENVIRONMENTS_ENABLED`, ~6k lines) in scope? | runtime controller, runtime API, runtime-kernel features |
| 6 | Is provider-native permission bypass intended, with an external sandbox assumed? | security posture of shell guard, approvals and docs |
| 7 | Voice in scope? | kokoro-onnx, supertonic, soundfile, Whisper, ElevenLabs; Python 3.12 pin |
| 8 | Knowledge v2 ingestion producer, embedding model and dimension | retrieval engine, sentence-transformers, pgvector dimension |
| 9 | Web scope: 5 locales, WebGL orb, generative UI, unreachable component families | i18n layer, three.js stack, ~12k dead lines |
| 10 | Is host-publishing port 8090 intended? | compose files, `authentication.md`, `cluster-mode.md` |
| 11 | Observability topology: aggregate metrics in the control plane or expose worker ports? | prometheus_client usage, observability overlay, OpenTelemetry |
| 12 | Is the Docker-free local-native install path supported? | install docs, missing `dev-up.sh`/`dev-down.sh` |
