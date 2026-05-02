# Production Deployment & Multi-Tenant Scaling Roadmap

> **Status**: planning document, not yet executed.
> Last updated: 2026-05-01.
> Purpose: future-reference roadmap for evolving the local-native koda into an enterprise-grade SaaS capable of serving multiple teams, squads, and workspaces with thousands of agents.

## Context

Today koda is a **single-node, single-supervisor, single-tenant runtime**. It runs beautifully for one operator (or a small team sharing a host) and the architectural choices reflect that — process-per-agent isolation, shared in-process Postgres, monolithic sidecars, in-process secrets vault. Every layer has been built to be *correct* on one host; none has been built to be *redundant, sharded, or geo-distributed*.

The goal of this document is to:

1. Catalog every weakness that blocks a multi-tenant production deployment, with file/line citations so future work can find the exact code surface.
2. Sketch the target architecture (what does "production-grade koda for an enterprise" look like).
3. Lay out a phased roadmap so the migration can happen incrementally without forking the codebase.
4. Surface the decision points the operator needs to make before any of this is implemented.

This is not a one-quarter project. A realistic timeline is **9–18 months** from start to a fully multi-region, multi-tenant SaaS. The phases below are designed so each one ships independently — you can stop after Phase 1, Phase 2, etc. and still have a usable, more-robust koda.

---

## Current State (Single-Node Snapshot)

### Process model

- **Supervisor** (`koda/control_plane/supervisor.py`): single instance, owns a `dict[agent_id, _WorkerState]` of all workers on the host. Reconcile loop polls every `CONTROL_PLANE_POLL_INTERVAL_SECONDS` (currently augmented by the lifecycle event from `koda/control_plane/lifecycle_events.py`).
- **Worker per agent**: each agent is a child Python process spawned via `asyncio.create_subprocess_exec` (line 235 of supervisor). Process boundary is the strongest isolation we have.
- **Sidecars**: 5 Rust binaries (`koda-security-service`, `koda-runtime-kernel`, `koda-memory-engine`, `koda-retrieval-engine`, `koda-artifact-engine`) — single instance each on the host.
- **Web**: Next.js dev server (`apps/web`) for the control-plane UI.
- **Storage**: single Postgres (default `127.0.0.1:5433`) + single MinIO (`127.0.0.1:9000`) + local filesystem.

### Data layer

- All koda tables live in `knowledge_v2` schema of one Postgres instance.
- Tenant isolation is **logical only** — `agent_id` (and increasingly `workspace_id`/`squad_id`) columns enforce scope via `WHERE` clauses in application code.
- Object storage is a single MinIO bucket; per-agent isolation enforced by the `validate_scoped_object_key(agent_scope, key)` helper in `rust/koda-security-core/src/lib.rs:150`.
- Migrations apply on boot via `_run_migrations` in `koda/knowledge/v2/postgres_backend.py`.

### Auth & secrets

- Operator login is single-account (`docs/security/authentication.md`). Argon2id password + 7-day session cookie sealed with AES-256-GCM. **One operator owns the whole host.**
- Provider API keys + per-agent secrets stored in `cp_secret_values` (encrypted with Fernet using `${STATE_ROOT_DIR}/control_plane/.master.key`). Master key on disk with 0600 perms.
- Channel tokens (Telegram bot, Slack, etc.) bound to agents via `cp_agent_connections`.

### Observability

- Prometheus metrics emitted via `koda/services/metrics.py` (per-agent labels exist).
- Structured logs via `structlog` to stdout / `~/.koda-local/var/log/`.
- Audit events (`audit_events` table) for security/compliance with retention `AUDIT_RETENTION_DAYS=90`.
- **No** distributed tracing, no log shipping, no central metrics aggregator out of the box.

### Deployment

- `~/.koda-local/scripts/dev-up.sh` is the canonical bring-up. Spins up postgres, minio, sidecars, control plane, web — all on one host.
- `docker-compose.{yml,prod.yml,dev.yml}` exist for container deployment but still single-host.

---

## Weaknesses Catalog

Severity rubric: **P0** = blocks any multi-tenant deployment; **P1** = blocks reliable production; **P2** = blocks scale; **P3** = blocks polish/UX/cost optimization.

### P0 — Single points of failure

| ID | Weakness | Location | Why it blocks production |
|---|---|---|---|
| P0-1 | **Single supervisor** owning all workers | `supervisor.py:60-65` | If supervisor crashes, no agent can be spawned/restarted. Active workers keep running but new messages don't surface (control-plane HTTP also dies). No HA. |
| P0-2 | **Single Postgres** for all tenants | `~/.koda-local/env` `POSTGRES_URL` | One slow query / vacuum / disk-full incident takes down every agent on the host. No replicas, no automatic failover. |
| P0-3 | **Single sidecar instance per kind** | `dev-up.sh:88-120` | `koda-security-service` blocking on a slow gRPC call freezes ALL workers (we observed this in pause/activate debugging — main thread deadlocks on shared `_pthread_cond_wait`). Five sidecars × N workers = N²-ish lock-correlation. |
| P0-4 | **Single operator account** | `docs/security/authentication.md` | No multi-user RBAC. Cannot restrict squad A from reading squad B's agents. |
| P0-5 | **Master key on local disk** | `koda/control_plane/crypto.py` (Fernet, file path) | Cannot rotate without coordinated downtime; not auditable; no HSM/KMS option. |
| P0-6 | **Workspace/squad fields exist but aren't enforced** | `cp_agent_definitions.workspace_id`/`squad_id` (nullable, advisory) | A request authenticated as squad A can read squad B's agent rows because no policy gate validates the workspace claim against the row's `workspace_id`. RLS not enabled. |

### P1 — Reliability / operability

| ID | Weakness | Location | Why it hurts |
|---|---|---|---|
| P1-1 | **Lazy migrations on boot** | `postgres_backend.py:_run_migrations` | A bad migration ships in a release and every host runs it on next boot, with no canary. Today's pause/activate debugging was caused by missing migration `019b` — found at runtime. |
| P1-2 | **Drop-pending-updates on every Telegram boot** | `__main__.py:724` (`run_polling(drop_pending_updates=True)`) | Restart loses in-flight messages users sent. No replay buffer. |
| P1-3 | **No health check beyond `/health` returning workers list** | `supervisor.py:_health` | No per-agent liveness / readiness, no provider-connectivity SLO probe. |
| P1-4 | **Worker restart on schema/runtime error is silent** | observed: `UndefinedColumnError` made worker crash-loop without alerting | No alert; operator only notices because messages stop. |
| P1-5 | **No graceful drain** | `supervisor._stop_worker` SIGINTs + 5s grace, then SIGKILL | Forced kill drops in-flight LLM responses (we made the rollback safe for queue items, but not for partial agent_cmd loops). |
| P1-6 | **Pause rollback writes only `last_error`** | `manager._rollback_in_flight_queue_items_for_pause` | No structured event for audit trail; replay logs hard to correlate. |
| P1-7 | **No checkpointing of LLM streams** | `koda/services/queue_manager.py` | Pause/restart re-runs the user query from scratch — wasteful at scale where queries cost real money. |

### P2 — Horizontal scaling

| ID | Weakness | Location | Why it hurts |
|---|---|---|---|
| P2-1 | **Supervisor is host-local** — no agent placement across hosts | `supervisor.py` | Cannot run koda on a fleet. A host's CPU/RAM is the hard ceiling for total agent count. |
| P2-2 | **Sidecars are 1× per host, called via UDS / loopback** | `RUNTIME_KERNEL_SOCKET` UDS, gRPC `127.0.0.1:port` | Sidecars cannot be a remote pool; shipping them to a separate node requires URL-aware client code. |
| P2-3 | **Connection pooling is per-worker** | asyncpg pools spawned by each worker | At 50 workers × 5 conn/pool = 250 Postgres connections on one host. Default `max_connections=100` exhausted. No central pgbouncer. |
| P2-4 | **MinIO is a single endpoint** | `KNOWLEDGE_V2_S3_ENDPOINT_URL` env | No object-store sharding; backup/restore is one-shot for the whole tenant set. |
| P2-5 | **Reconcile loop is O(N agents)** | `supervisor._reconcile_once` iterates `manager.list_agents()` | At 10k agents, every poll cycle is a 10k-row query + 10k worker checks. Not linearizable for scale. |
| P2-6 | **Per-agent telegram polling = 1 long-poll TCP socket per agent** | python-telegram-bot internal | At 10k agents = 10k persistent TCP connections to Telegram. Goes against fan-in patterns; Telegram rate-limits per bot, not per polling client. |

### P2 — Multi-tenancy

| ID | Weakness | Location | Why it hurts |
|---|---|---|---|
| P2-7 | **No quota per workspace** | n/a (not implemented) | A noisy agent in workspace A can starve workspace B's queue, LLM spend, and DB connections. |
| P2-8 | **No cost attribution by squad/workspace** | `cost_usd` per task tracked, but no rollup | Cannot show "Squad X consumed $42k of LLM cost this month." |
| P2-9 | **Secrets not workspace-scoped** | `cp_secret_values.scope_id` is `"global"` or `agent_id` (line 1258, postgres_backend) | An operator can see ALL secrets. No squad-admin role with bounded visibility. |
| P2-10 | **No data-residency controls** | DB / S3 are single-instance | Cannot tell workspace A "your data lives in EU only." Compliance blocker for GDPR/LGPD/HIPAA. |
| P2-11 | **Audit log is a single table** | `audit_events` | At enterprise scale, regulators want per-tenant export and retention overrides. |

### P3 — Polish, observability, devex

| ID | Weakness | Why it hurts |
|---|---|---|
| P3-1 | No distributed tracing across worker → sidecar → DB | Hard to root-cause cross-process latency |
| P3-2 | No SLO dashboard or alerting baseline | Operator finds out things are broken from end users |
| P3-3 | No blue/green or canary deploy story | Risky updates |
| P3-4 | Schema migrations have no rollback | Bad migration is a one-way door |
| P3-5 | No native i18n for tenant-facing UI strings beyond pt-BR/en | Onboarding non-Portuguese teams requires translation work |
| P3-6 | Provider model catalog refresh is manual (we just did 7) | Adding GPT-N+1 / Claude N+1 needs a code+deploy cycle |

---

## Target Architecture

The state we are evolving towards. Each piece is modular — implementing them in different orders is fine as long as the contracts hold.

### Control plane

- **Stateless control-plane API tier** behind a load balancer. Each replica reads/writes Postgres only; no in-process worker dict.
- **Supervisor cluster**: N supervisor instances using a leader-elected work queue (Postgres `SELECT … FOR UPDATE SKIP LOCKED` is enough for first cut; etcd/Consul/Redis Streams for second cut). Each supervisor "claims" agents to host.
- **Agent placement**: a small scheduler decides which supervisor hosts which agent. Inputs: per-agent CPU/RAM hints, host capacity, workspace data-residency hints, anti-affinity rules.

### Data plane

- **Postgres HA**: primary + 2 replicas (streaming replication), pgbouncer in front for connection multiplexing, automated failover (Patroni / RDS).
- **Logical separation per tenant**: row-level security (RLS) policies on every koda table, keyed on `workspace_id`. Application sets `SET LOCAL app.workspace_id = '…'` per request.
- **Optional physical separation**: large tenants get their own database (or schema) — same code path, different DSN per workspace.
- **MinIO replicaset / S3-compatible managed bucket** with per-workspace prefix + encryption keys (per-workspace KMS keys).

### Sidecars

- Sidecars containerized and deployed as their own service (Kubernetes Deployment + Service or equivalent). Workers connect via `*_GRPC_TARGET` URLs that resolve to a load-balanced pool, not localhost.
- Each sidecar horizontally scaled independently. Stateless or with externalized state (e.g., security-service is stateless; memory-engine writes to Postgres + S3, both shared).

### Auth & secrets

- **Multi-user with workspace RBAC**: roles = `org_admin`, `workspace_admin`, `squad_admin`, `operator`, `viewer`. Identity via OIDC / SAML (Okta, Azure AD, Google Workspace).
- **Service-to-service auth**: mTLS between control plane / sidecars / workers. Short-lived JWTs from a trust anchor service.
- **Secrets vault**: replace local Fernet with HashiCorp Vault or AWS KMS / GCP KMS. Per-workspace encryption keys, automated rotation, full audit trail.

### Observability

- OpenTelemetry trace context propagated from web → control-plane → worker → sidecar → DB. Sampled traces shipped to Tempo / Honeycomb / Datadog.
- Metrics aggregated centrally (Prometheus federation or Mimir / Cortex).
- Structured logs shipped to a central store (Loki / ELK / Datadog).
- Per-tenant SLO dashboards: message processing p50/p99, provider latency, queue depth, error budget.

### Cost & quotas

- Each workspace has a quota policy: max agents, max msg/s, monthly LLM spend cap, allowed providers/models.
- Cost ledger appended to `audit_events` rolled up nightly per workspace/squad.
- Hard stop when monthly cap hit; soft warning at 80%.

### Network & ingress

- TLS terminated at ingress (Envoy / Traefik / cloud LB). Webhook URLs unique per workspace.
- Telegram polling consolidated into a **bot-pool service** that fan-outs updates to the right worker by `agent_id` mapping — eliminates 1-TCP-per-agent fan-out.
- Rate limits at edge (per workspace and per global).

### Multi-region

- One koda "region" = one full stack (control plane + sidecars + DB + S3) deployed in a single cloud region.
- Cross-region: workspace assignment to a home region. User data never crosses region boundaries unless explicitly opted in.
- Web app uses a tenant-aware router that proxies to the correct region.

---

## Phased Roadmap

Each phase is independent. Stop at any point and you have a useful improvement.

### Phase 0 — Stabilization (2–4 weeks)

**Goal**: fix the foot-guns we hit during local debugging this week. No architectural change.

- [ ] Migrations applied in a deterministic CI step (not lazy on first boot). Add `koda migrate` CLI command. Ref P1-1.
- [ ] Health endpoint returns granular status: per-agent worker state, DB pool stats, sidecar latency. Ref P1-3.
- [ ] Alert hook: write a webhook (or just a structured `audit_events` entry) when a worker crash-loops > N times in M minutes. Ref P1-4.
- [ ] Replace `drop_pending_updates=True` with a per-bot offset stored in DB so restarts don't lose user messages. Ref P1-2.
- [ ] Document the dev-up.sh PID-file invariant; add `dev-restart.sh` that gracefully handles minio "already running". Ref today's debugging.
- [ ] Pause/resume audit event (structured) instead of just `last_error` marker. Ref P1-6.

**Deliverable**: a single-node koda that doesn't lose messages on restart, alerts on crash-loop, and migrates on a deliberate command.

### Phase 1 — Vertical scaling (1–2 months)

**Goal**: squeeze every drop out of one host. Foundation for horizontal later.

- [ ] **pgbouncer in front of Postgres** with transaction pooling. Workers connect via pgbouncer (`POSTGRES_URL` env points to pooler). Ref P2-3.
- [ ] **Connection pool tuning**: workers cap their asyncpg pool to `max(2, ceil(MAX_CONCURRENCY / 4))`. Ref P2-3.
- [ ] **Sidecar connection reuse**: gRPC channels pooled per worker, not per RPC call.
- [ ] **Reconcile loop incremental**: supervisor only reconciles agents whose `updated_at` changed since last poll, plus a full sweep every K minutes. Ref P2-5.
- [ ] **Worker resource limits**: cgroup / OS-level memory cap per worker. Crash early instead of OOM-killing the host.
- [x] **Bot-pool prototype**: single process that polls all Telegram bots and dispatches updates to the right worker via gRPC. Ref P2-6. _Shipped as `koda-bot-gateway` (Phase 1B). Opt-in via `BOT_GATEWAY_ENABLED=true`. Durable per-agent queue in `cp_telegram_pending_updates` (migration 021); at-least-once delivery via subscribe + acknowledge. Workers consume through `koda/runtime/bot_gateway_runner.py`._
- [x] **Workspace policy engine**: per-workspace rate limit, concurrent-agent slots, monthly LLM spend cap. Ref P2-7/P2-8. _Shipped as `koda-policy-engine` (Phase 1C). Token-bucket sub-ms decision; Postgres-backed spend ledger + monthly window in migration 022. Python wrapper `check_ingest_or_allow` / `record_spend_safe` falls through permissively on outage so the bot-gateway's at-least-once delivery never gets nullified. Opt-in via `POLICY_ENGINE_ENABLED=true`._
- [x] **Circuit breaker for internal_rpc**: per-upstream sliding-window breaker so a hung sidecar fails worker calls in microseconds instead of waiting on `INTERNAL_RPC_DEADLINE_MS`. Ref P0-3. _Shipped as `koda/internal_rpc/circuit_breaker.py` (Phase 1D). Closed → open → half-open state machine with cooldown; process-local registry one-per-upstream. Pragmatic Python alternative to a full Rust proxy; the contract supports moving state to a shared store later for cluster-wide coordination._
- [x] **OS-level isolation hooks**: cgroup v2 + cpu pinning per workspace cgroup. Ref "isolamento além de lógico". _Shipped as `koda-runtime-kernel/src/isolation.rs` (Phase 1E) + Python wrapper `koda/control_plane/isolation_runtime.py` (Phase A.3 wire-up). Supervisor calls `ensure_cgroup_v2_root → apply_workspace_limits → spawn → place_pid` so an OOM kills the offending workspace cgroup instead of the host. Defaults from `KODA_AGENT_DEFAULT_{MEMORY_MB,CPU_FRACTION,PIDS_MAX}`. Sanitizer rejects path-traversal. macOS no-op._
- [x] **Wire-up consumption** (Phase A): every component built in Phases 0+1+2 is now actually invoked by the runtime. _Shipped as Phase A.1-A.6: queue_manager calls policy_engine on ingest + records spend post-LLM; 5 internal_rpc clients × 35 sites wrap every call with circuit breaker (1.000.000× fail-fast vs 1500ms deadline); supervisor spawns workers under cgroup limits; tracing init in worker + supervisor entrypoints; heartbeat task independent of reconcile; central `blocked_patterns` registry with hygiene grep gate. Bench: command_guard 25× vs Python re._
- [x] **Formal benchmarks with regression gates** (Phase B.3). _Shipped as `tests/benchmarks/` with JSON baselines: command_guard 102ns/op, breaker closed 859ns/op, breaker open 907ns/op, tracing no-op 452ns/op. CI fails when any bench exceeds the baseline._
- [x] **Operator runbooks** (`docs/operations/`). _Shipped (Phase C): backup-restore, upgrade, cluster-mode, incident-response, observability, hardening — covers every scenario a self-hoster needs from "first deploy" through "stable at scale" with concrete commands._
- [x] **Real-Postgres test fixture** (Phase B.1). _Shipped as `tests/postgres_fixtures.py`: session-scoped `postgres_url` resolves from `POSTGRES_TEST_DSN` env (CI) or testcontainers + Docker (local); auto-skip when neither is available; per-test `db_connection` rolls back transactions for isolation. `@pytest.mark.postgres` marker registered._
- [x] **Multi-host cluster compose** (Phase D). _Shipped as `docker-compose-cluster.yml` overlay + `scripts/cluster_smoke.sh`. Activates `KODA_CLUSTER_MODE=cluster` on N app replicas, scales heavy sidecars (memory, retrieval) for pool failover via Phase 2B service-discovery, applies `KODA_AGENT_DEFAULT_*` cgroup limits. Smoke script validates registration, claim distribution, drain protocol, and sidecar pool resilience._
- [x] **Observability stack overlay** (Phase E). _Shipped as `docker-compose-observability.yml` + Prometheus scrape config + 8 alert rules + Tempo OTLP receiver + Grafana datasource provisioning. Self-hoster brings up the full triple (metrics + logs + traces) with one compose flag._
- [x] **Hardening gate** (Phase F). _`scripts/doctor.py --strict` adds 11+ hardening checks (token strength, file perms, auth mode, audit retention, browser sandbox, cgroup root) matching `docs/operations/hardening.md`. CI gate refuses a release whose `.env` baseline regresses any check._
- [x] **Cross-platform CI matrix** (Phase B.4). _`pr-quality.yml` adds macos-14 to the python-tests matrix. Catches darwin-only regressions in cgroup no-op paths, isolation cfg-gated code, and path handling._
- [x] **Live Rust binary integration tests** (Phase B.2). _`tests/integration/` spins real cargo-built binaries via the `spawn_rust_binary` fixture and exercises Python clients against them. Ships with bot-gateway register/subscribe/ack roundtrip + idempotency tests; framework reusable for policy-engine and runtime-kernel additions._
- [x] **Triple-check workflows** (Phase G). _`.github/workflows/{benchmarks.yml,release-quality.yml}` gate every release: lint+format+mypy+pytest+coverage; cargo fmt+clippy+test; web lint+test+build; migrations gate; doctor --strict; benchmark regression. A failed step blocks the tag._
- [ ] **Postgres tuning**: `max_connections`, `shared_buffers`, `effective_cache_size` matched to host.

**Deliverable**: a single host comfortably running 500 agents.

### Phase 2 — Horizontal scaling (3–4 months)

**Goal**: agents distributed across N hosts. Stateless control plane.

- [ ] **Stateless control-plane API**: extract HTTP layer from supervisor; multiple replicas behind LB. _Partially shipped: each supervisor instance now exposes `/cluster/{status,drain,undrain}` and runs only agents it has claimed; full HTTP-tier extraction (separate API process behind LB) remains an operational packaging step._
- [x] **Supervisor cluster with leader-elected work queue**: each supervisor claims agents via `SELECT … FOR UPDATE SKIP LOCKED` on a `cp_agent_assignments` table. Ref P2-1. _Shipped as `koda/control_plane/cluster.py` (Phase 2A). Migration 024 adds `cp_agent_assignments` + `cp_supervisor_runtimes`. Activate via `KODA_CLUSTER_MODE=cluster`; supervisor reconcile narrows the active set to claimed agents and refreshes heartbeats every poll._
- [x] **Sidecars containerized + service-discovery**: workers connect to `<sidecar>.svc.cluster.local` instead of UDS / 127.0.0.1. Ref P2-2. _Shipped (Phase 2B): `*_GRPC_TARGET` accepts comma-separated endpoint pools; `resolve_grpc_target` translates them to gRPC's `ipv4:` resolver and the channel is built with the round-robin LB policy. Single-target paths stay zero-overhead._
- [ ] **Postgres HA**: primary + replica + automated failover (Patroni or managed RDS). Ref P0-2. _Operational decision (Patroni / RDS / Crunchy)._
- [ ] **MinIO replicaset / managed S3**: erasure-coded, with workspace-prefix encryption. _Operational decision._
- [x] **Distributed tracing**: OpenTelemetry traces from web → API → worker → sidecar → DB. Ref P3-1. _Scaffold shipped as `koda/observability/tracing.py` (Phase 2D). Zero hard dep — `init_tracing` opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT`. `start_span`, `inject_grpc_context`, `extract_grpc_context` degrade to no-ops when the SDK is missing. Per-call instrumentation of queue_manager + sidecars is incremental from here._
- [x] **Schema migrations gated by CI**: a release pipeline applies migrations before rolling new code. _Shipped (Phase 2C): `python -m koda migrate --check` returns exit-3 when pending migrations exist, exit-1 on infra error. `.github/workflows/migrations-gate.yml` wires it against an ephemeral pgvector service before merge._
- [x] **Blue/green deploy**: supervisor cluster supports two versions side-by-side, drains old workers when new version healthy. _Shipped (Phase 2E): `POST /cluster/drain` flips `cp_supervisor_runtimes.draining=true`; the cluster module then RELEASES every claim on next heartbeat instead of refreshing, so siblings pick up ownership without losing in-flight work._

**Deliverable**: 5k–10k agents across a fleet, with no single host being a SPOF.

### Phase 3 — Multi-tenancy (3–5 months, can overlap with Phase 2)

**Goal**: multiple companies / business units share one cluster, with hard isolation.

- [ ] **Multi-user auth**: OIDC/SAML provider integration. Identity table + RBAC table. Ref P0-4.
- [ ] **Workspace boundary enforcement**: every read/write goes through a policy gate that asserts `request.workspace_id == row.workspace_id`. Add Postgres RLS as a defense-in-depth. Ref P0-6.
- [ ] **Workspace-scoped secrets**: extend `cp_secret_values.scope_id` to support `workspace:<id>` scope; apply RLS. Ref P2-9.
- [ ] **Quotas service**: enforced at API + at queue dequeue (`max_concurrent_agents_per_workspace`, `max_messages_per_minute`, `max_monthly_llm_spend_usd`). Ref P2-7.
- [ ] **Cost attribution**: per-message cost tagged with `workspace_id`/`squad_id`; nightly rollup → `cp_cost_ledger`. Ref P2-8.
- [ ] **Workspace-aware UI**: web app reads token claims, scopes every query, hides inaccessible content. Existing workspace/squad fields finally get enforced.
- [ ] **Audit per tenant**: `audit_events` partitioned by `workspace_id`, with per-tenant retention and export. Ref P2-11.
- [ ] **Secrets vault integration**: replace Fernet with Vault / KMS, per-workspace data keys. Ref P0-5.

**Deliverable**: koda runs as a SaaS — one cluster serves multiple companies, with hard data and operational isolation.

### Phase 4 — Multi-region & data residency (2–3 months)

**Goal**: workspace can live in EU / US / SA region by policy.

- [ ] **Per-region stacks**: full koda deploy per region (EU, US, SA, etc.).
- [ ] **Tenant routing**: a thin global "tenant locator" knows which region a workspace lives in. Web app and API gateway route requests there.
- [ ] **Data residency contracts**: workspaces never replicate across region boundaries. Backup/DR also per-region.
- [ ] **Cross-region disaster recovery**: warm-standby region with async replication for workspaces that opt in (paid tier).
- [ ] **Compliance certifications**: SOC 2 Type II, ISO 27001, GDPR/LGPD residency, HIPAA-ready (BAA workflow) all gated on this phase.

**Deliverable**: enterprise-grade multi-region SaaS with compliance posture.

### Phase 5 — Operational maturity (continuous)

- [ ] SLO dashboards per tenant (p50/p99 message latency, error rate, queue depth, provider success rate).
- [ ] Error budget alerts → on-call rotation.
- [ ] Chaos engineering: scheduled failure injection (kill a sidecar, drop DB connection) to validate recovery.
- [ ] Cost optimization: spot instances for stateless workers, autoscaling based on queue depth.
- [ ] Provider catalog auto-refresh: nightly job pulls vendor pricing pages, opens PR with diffs.

---

## Key Decisions (operator must answer before each phase starts)

1. **Cloud or self-hosted?** Self-hosted means we build pgbouncer/HA tooling; managed means we delegate to RDS/Cloud SQL/etc. and lose some control.
2. **K8s or Nomad / ECS / VM-based?** Affects sidecar deployment, supervisor cluster shape, and what "stateless" means.
3. **Vault or cloud KMS for secrets?** Determines secret rotation cadence, cost, and audit story.
4. **OIDC IdP**: bring-your-own-Okta vs. ship our own with social login? Affects squad/workspace onboarding flow.
5. **Pricing model**: per-agent, per-message, per-workspace flat? Drives quotas + cost-attribution shape.
6. **Compliance scope**: SOC 2 only? GDPR + LGPD? HIPAA? Each adds work in Phase 3-4.
7. **Multi-region threshold**: how many EU customers triggers building Phase 4? (Likely "2nd customer asks" — better to plan early.)
8. **Tenant onboarding self-serve or sales-assisted?** Self-serve requires polished UX + automatic provisioning; sales-assisted lets us ship faster with manual workspace setup.

---

## Migration Strategy (don't fork the codebase)

The single-node koda must keep working through every phase. Strategy:

- **Feature flags for cluster mode**: a `KODA_CLUSTER_MODE=single|cluster` env. Single-node default behaves exactly as today. Cluster-mode unlocks the new code paths.
- **Backwards-compatible schema**: every migration is additive (add columns, add tables; never drop or rename in a single deploy). Two-phase removals only.
- **Sidecars listen on UDS by default, gRPC over TCP when env set**: existing dev-up.sh keeps working; cluster deploys override.
- **DB DSN abstraction**: workers read DSN from env. Single-node points to localhost; cluster points to pgbouncer; multi-region points to a region-aware DSN resolver.
- **Documentation contract**: every new env var goes into `.env.example` with a `# (cluster only)` marker.

Result: an OSS user can run `dev-up.sh` and get a single-node koda forever; a SaaS operator flips flags and gets the production deployment.

---

## Operational Baseline (must exist before SaaS launch)

Even Phase 1 should land with these:

- **Runbooks** for: pause/resume agent, rotate provider key, restore from backup, failover Postgres primary, evacuate a host.
- **On-call rotation** with PagerDuty / Opsgenie integration.
- **Status page** (statuspage.io / cstate / homemade) showing per-region health.
- **SLA targets** documented and instrumented: e.g., 99.9% message-acceptance, p99 ≤ 30s for agent response start.
- **Backup tested monthly**: restore drill, not just "backups exist."
- **Security incident playbook**: revoke compromised key, force-logout user, lock workspace.

---

## Open Questions / Risks

- **Agent state at scale**: each agent worker holds an in-process queue + memory cache. If we want to migrate workers between hosts (rebalancing), we need to externalize that state. Cost: rewriting `koda/services/queue_manager.py` to be process-relocatable.
- **Provider rate-limiting**: at 10k agents calling Claude / OpenAI / Mistral, vendor rate-limits become the bottleneck. We may need a per-vendor proxy that pools requests.
- **Telegram fan-out**: bot-pool service (Phase 1) is the right answer, but Telegram doesn't expose a "subscribe to multiple bots" API — we'd be polling N bots from one process, which is the same problem at smaller scale. May need to split bot-pool into shards.
- **gRPC sidecar latency variance**: today it's localhost (0.1ms). Over the network it's 1–5ms per call. With agents making dozens of sidecar calls per turn, this adds up. Profile early.
- **Schema migrations on multi-region**: schema changes need to roll out region-by-region. A migration that takes 4 hours globally is a real coordination problem.
- **Provider model catalog drift**: vendors deprecate models faster than we can ship code. Need automation (Phase 5) or this becomes a tax on every release.

---

## Success Criteria (what "done" looks like for each phase)

| Phase | Success metric |
|---|---|
| 0 | Zero message loss across `dev-restart.sh`. Crash-loop alerts fire. Health endpoint shows per-agent status. |
| 1 | One host comfortably runs 500 agents at p99 ≤ 30s response. pgbouncer + sidecar pool tuned. |
| 2 | 5k agents across ≥3 hosts. Single host failure causes <1 min of degraded service. Distributed tracing in place. |
| 3 | 3+ companies share one cluster. Workspace A operator cannot read workspace B's anything. Cost report rolls up by squad. |
| 4 | Workspace assigned to EU region never replicates to US. SOC 2 Type II audit passes. |
| 5 | On-call rotations exist. SLO dashboards green. Chaos drills monthly. |

---

## Out of Scope for This Document

These are real concerns but require their own planning docs:

- **Mobile apps** (iOS / Android control plane companion).
- **Marketplace of agent templates** (pre-built squads to onboard a team in 5 min).
- **Self-hosting an LLM** (running an Ollama / vLLM cluster as part of koda).
- **Edge inference** for low-latency / offline scenarios.
- **Voice runtime at scale** (kokoro / elevenlabs at 10k concurrent calls).
- **IDE/editor integrations** (VS Code, JetBrains, Zed).

---

## Appendix A — Code surface inventory (touchpoints)

Files that will see significant change in each phase. Helps future-you scope work.

**Phase 0**:
- `koda/control_plane/supervisor.py` (health, alerts)
- `koda/__main__.py` (drop_pending_updates → DB-stored offset)
- `koda/control_plane/manager.py` (audit-event emission for pause/resume)
- `koda/knowledge/v2/postgres_backend.py` (CLI migrate command)

**Phase 1**:
- `koda/services/runtime/postgres_store.py` (pool size tuning)
- `koda/services/queue_manager.py` (concurrency limits)
- New: `koda/services/bot_pool.py` (Telegram fan-in service)
- `koda/internal_rpc/*.py` (gRPC channel reuse)

**Phase 2**:
- `koda/control_plane/supervisor.py` (cluster mode, leader election)
- `koda/control_plane/api.py` (extract from supervisor process)
- New: `koda/control_plane/scheduler.py` (agent placement)
- `dev-up.sh` → Helm chart / docker-compose-cluster.yml
- All sidecar `*_GRPC_TARGET` resolution code paths

**Phase 3**:
- `koda/auth.py` (OIDC, RBAC)
- `koda/control_plane/manager.py` (workspace policy gate everywhere)
- `koda/control_plane/crypto.py` (Vault / KMS adapter)
- `apps/web/src/lib/auth.ts` (token claims, RBAC checks)
- New: `koda/services/quotas.py`, `koda/services/cost_ledger.py`
- All ~30 koda tables (RLS policies)

**Phase 4**:
- New: `koda/control_plane/region_locator.py`
- DNS / ingress configuration (out of repo)
- Backup/DR scripts (out of repo)

---

## Appendix B — Naming things

For consistency when writing future code:

- **Tenant** = a customer organization. Owns one or more workspaces.
- **Workspace** = a logical scope a team operates within. Owns one or more squads. Has its own quotas, secrets, providers.
- **Squad** = a team / sub-org inside a workspace. Owns one or more agents. Has RBAC limits.
- **Agent** = a runtime instance. Has one Telegram bot (or other channel), one config, its own queue.
- **Region** = a geographic deployment of the full stack.
- **Cluster** = a single supervisor leadership domain within a region (typically 1:1 with region).
- **Worker** = an OS process running one agent's runtime.
- **Sidecar** = a Rust binary providing infra-level service (security, memory, retrieval, artifact, runtime-kernel).
- **Pod** = (when on K8s) a unit of scheduling; usually one supervisor pod or one sidecar pod.

---

## Where this document lives

`docs/architecture/production-deployment-roadmap.md` — versioned with the codebase, so future-you and future-collaborators can update the weakness catalog as code evolves. When a P-item is fixed, mark it `~~done~~` and link the PR.
