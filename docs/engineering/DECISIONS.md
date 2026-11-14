# Architecture Decision Log

The initial ADR log for the consolidation mission ([MISSION.md](MISSION.md) §5.3, §14). Each entry records a
significant consolidation decision drawn from the Phase Zero audit:
[ARCHITECTURE_AUDIT.md](ARCHITECTURE_AUDIT.md), [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md),
[FEATURE_MATRIX.md](FEATURE_MATRIX.md) and [SYSTEM_INVENTORY.md](SYSTEM_INVENTORY.md). The tasks that carry
each decision out are in [MASTER_PLAN.md](MASTER_PLAN.md).

## Conventions

| Status | Meaning |
|---|---|
| `proposed` | Waiting on an operator approval (MISSION §13), an open product decision (`Q-n`, MASTER_PLAN §5), or evidence named in the ADR. Work limited to what the ADR marks as interim may proceed. |
| `accepted` | In force. Either the operator approved it (date given), or it is a routine, reversible technical decision inside mission authority (MISSION §15), accepted by the Principal Architect. Every task carrying it out still gets independent review per MASTER_PLAN §8. |
| `superseded` | Replaced by a later ADR, which is named. |

An accepted ADR that a later ADR narrows, extends or partly replaces keeps `accepted`, and its status line
names the later ADR and the clause it changes. Revision 1 of the plan (2026-11-14) added ADR-028 to ADR-037
after an independent review of the first draft.

Rules:

- An accepted ADR is never edited in substance. To change it, add a new ADR that supersedes it.
- Each task records evidence in VALIDATION_REPORT.md. Accepting an ADR does not mean its tasks are done.
- Q-n refers to the decision register in MASTER_PLAN §5.1 (ARCHITECTURE_AUDIT §11 `D-n`, renamed).
- D-NNN and TD-NNN refer to TECHNICAL_DEBT.md, and F-* to FEATURE_MATRIX.md.

## Index

| ADR | Title | Status | Gate | Main tasks |
|---|---|---|---|---|
| [ADR-001](#adr-001--modular-monolith-runtime-kernel-is-the-only-rust-process) | Modular monolith; runtime-kernel is the only Rust process | accepted | Removals of documented opt-in sidecars need approval (Q-22) | M1-E6-T1, M5-E5-* |
| [ADR-002](#adr-002--agent-native-tool-governance-option-c) | Agent-native tool governance (Option C) | accepted (operator, 2026-11-14) | Key relocation and DB role need sign-off | M1-E2-* |
| [ADR-003](#adr-003--loopback-by-default-network-exposure) | Loopback-by-default network exposure | accepted (operator, 2026-11-14); implemented, CI evidence pending | — | M1-E1-T1 (in review) |
| [ADR-004](#adr-004--one-migration-registry-and-runner) | One migration registry and runner | accepted; amended by ADR-028 | — | M2-E2-T2, M2-E2-T5, M2-E2-T6, M5-E1-T1 |
| [ADR-005](#adr-005--one-execution-intake-strangler-split-of-queue_manager) | One execution intake; strangler split of `queue_manager` | accepted | — | M5-E2-T1..T4 |
| [ADR-006](#adr-006--one-retry-and-error-policy-working-circuit-breakers) | One retry and error policy; working circuit breakers | accepted | — | M2-E4-T1, M3-E8-T2, M5-E2-T5 |
| [ADR-007](#adr-007--one-tool-catalog) | One tool catalog | accepted | — | M1-E4-T5, M5-E3-T1, M5-E3-T18 |
| [ADR-008](#adr-008--one-execution-policy-evaluator) | One execution-policy evaluator | proposed | Q-5, §13 | M1-E4-T9, M5-E3-T2, T3, T5, T12..T17, T19 |
| [ADR-009](#adr-009--one-approval-pipeline-persisted-in-postgres) | One approval pipeline, persisted in Postgres | accepted | Going live (M3-E3-T1) needs approval | M2-E1-*, M3-E3-*, M5-E3-T4, M6-E2-T5 |
| [ADR-010](#adr-010--security-primitives-in-process-one-of-each) | Security primitives in process, one of each | accepted; command-guard clause proposed for supersession by ADR-033 | — | M1-E3-*, M1-E4-T13, M5-E3-T8, M5-E5-T1 |
| [ADR-011](#adr-011--cross-process-state-only-through-postgres-or-the-worker-runtime-api) | Cross-process state only through Postgres or the worker runtime API | accepted | — | M3-E3-T2, M3-E6-T6, M5-E7-T5 |
| [ADR-012](#adr-012--async-repositories-replace-the-sync-bridge-on-hot-paths) | Async repositories replace the sync bridge on hot paths | accepted | — | M2-E2-T4, M5-E1-T2..T4, M9-E3-T9 |
| [ADR-013](#adr-013--one-configuration-surface-enforced-in-ci) | One configuration surface, enforced in CI | accepted; registry clauses superseded by ADR-036 | — | M4-E1-T2, M5-E4-T1, M5-E4-T3 |
| [ADR-014](#adr-014--memory-in-python-sql-with-postgres-full-text-search) | Memory in Python SQL with Postgres full-text search | proposed | Spec tests and comparison (Q-7) | M3-E4-*, M5-E5-T3, T4, T10 |
| [ADR-015](#adr-015--knowledge-v2-scope) | Knowledge v2 scope | proposed | Q-6; removal needs approval | M6-E1-T4 (decision), M6-E1-T5, M6-E1-T10 |
| [ADR-016](#adr-016--squads-keep-the-core-consolidate-the-plumbing) | Squads: keep the core, consolidate the plumbing | accepted | Default-on stays Q-9 | M1-E5-T1, M1-E5-T4, M3-E6-*, M5-E7-*, M9-E3-T10 |
| [ADR-017](#adr-017--channels-telegram-is-the-only-live-channel) | Channels: Telegram is the only live channel | proposed | Q-2 (batch 1), Q-3 | M3-E5-T3, M6-E1-T2, T3, M5-E8-T5 |
| [ADR-018](#adr-018--deletion-policy) | Deletion policy | accepted; clarified by ADR-037 | — | M4-* |
| [ADR-019](#adr-019--one-error-envelope-openapi-as-the-contract-source) | One error envelope; OpenAPI as the contract source | accepted; amended by ADR-030 | — | M5-E6-T1, T10, T12 |
| [ADR-020](#adr-020--web-data-layer-and-outage-semantics) | Web data layer and outage semantics | accepted | — | M3-E8-T3, M5-E8-* |
| [ADR-021](#adr-021--delivery-consolidation) | Delivery consolidation | accepted | Project-name change needs approval | M1-E7-T1, T5, M5-E5-T8, T9, M7-E4-T1 |
| [ADR-022](#adr-022--single-host-deployment) | Single-host deployment | proposed | Q-1, §13 | M1-E1-T15, M5-E2-T9, T10, M5-E6-T9, M5-E6-T13 |
| [ADR-023](#adr-023--agent-deletion-semantics) | Agent deletion semantics | proposed | Q-11, §13 | M2-E3-T2, T3 |
| [ADR-024](#adr-024--data-retention-and-privacy) | Data retention and privacy | proposed | §13 (destructive) | M2-E5-* |
| [ADR-025](#adr-025--signing-key-separation-and-secret-references-in-snapshots) | Signing-key separation and secret references in snapshots | accepted | — | M1-E6-T3, M5-E6-T7 |
| [ADR-026](#adr-026--master-key-relocation-and-rotation) | Master-key relocation and rotation | proposed | §13 (secrets) | M1-E2-T3, M5-E6-T11, M2-E6-T1 |
| [ADR-027](#adr-027--test-strategy-for-the-consolidation) | Test strategy for the consolidation | accepted | — | M0-*, M9-E3-T5 |
| [ADR-028](#adr-028--online-migrations-and-a-lock-budget) | Online migrations and a lock budget (amends ADR-004) | accepted | — | M2-E2-T2, M2-E2-T5, and every index or backfill migration |
| [ADR-029](#adr-029--a-proven-restore-precedes-destructive-or-irreversible-change) | A proven restore precedes destructive or irreversible change | accepted | — | M2-E6-T1, M2-E6-T2, every task marked "Restore" in MASTER_PLAN §5.2 |
| [ADR-030](#adr-030--external-contract-changes-one-release-window-changelog-in-the-same-change) | External contract changes: one-release window, changelog in the same change (amends ADR-019) | accepted | — | M5-E6-T1, T8, T12, M10-E1-T3 |
| [ADR-031](#adr-031--learning-definition-and-measurable-behaviour) | Learning: definition and measurable behaviour | proposed | Evidence from M6-E4-T1 | M3-E4-T7, M6-E4-T1, T2 |
| [ADR-032](#adr-032--squad-orchestration-semantics) | Squad orchestration semantics | proposed | Tests in M3-E6-T7 | M3-E6-T7, M3-E2-T4, M3-E2-T5 |
| [ADR-033](#adr-033--one-command-guard-at-the-runtime-kernel) | One command guard, at the runtime kernel | proposed | Spike in M5-E3-T6 | M1-E4-T10, M5-E3-T6, M5-E5-T1 |
| [ADR-034](#adr-034--the-mcp-client-stays-on-the-shared-aiohttp-stack) | The MCP client stays on the shared aiohttp stack | accepted | — | M1-E3-T3, M5-E3-T10 |
| [ADR-035](#adr-035--runtime-kernel-rpc-token-holders-and-threat-scope) | Runtime-kernel RPC token: holders and threat scope | proposed | §13 (credentials; deployment change) | M1-E6-T1, M1-E2-T4 |
| [ADR-036](#adr-036--configuration-drift-is-caught-by-a-parity-test) | Configuration drift is caught by a parity test (supersedes part of ADR-013) | accepted | — | M5-E4-T2 |
| [ADR-037](#adr-037--deletion-policy-clarifications) | Deletion policy clarifications (clarifies ADR-018) | accepted | — | M4-*, M1-E8-*, M7-E3-T3 |

---

## ADR-001 — Modular monolith; runtime-kernel is the only Rust process

- **Status:** accepted (2026-11-14, Principal Architect). Removing the documented opt-in sidecars stays `needs-approval` (Q-22). ADR-035 records who holds the kernel token and why it needs approval.
- **Context:**
  - The default stack runs 10 containers.
  - 5 to 7 Rust gRPC sidecars read and write one Python-owned Postgres schema through hand-written SQL. They have no RPC authentication and ship in lockstep.
  - A Python migration can break a sidecar at runtime.
  - The security sidecar is a synchronous network hop for pure functions and a hard availability dependency.
  - The memory and retrieval engines do lexical scans of at most 400 rows, or run over empty tables.
  - Only the runtime-kernel owns OS resources (child processes, PTYs, browsers). See ARCHITECTURE_AUDIT §3.5 and §7.2, and TD-112.
- **Decision:** a component keeps its own process only if it passes at least one of four tests, with evidence:
  1. it owns OS resources;
  2. it is a trust boundary with different credentials;
  3. it meets a measured performance requirement that in-process Python cannot;
  4. it is actually deployed or scaled independently.

  The target processes are `web`, `app`, the agent workers (children of the kernel), `runtime-kernel`, `postgres` and `seaweedfs` with its init job. Security and artifact fold into Python. Memory follows ADR-014 and retrieval follows ADR-015. The command-guard crate is removed as never shipped.

  The sidecars that are about to be folded get **no** interim auth tokens. Agent code runs inside the runtime-kernel container, which would hold any such token. Only the kernel boundary is hardened (UDS plus token), and web leaves the backend network.
- **Alternatives considered:**
  - Keep all sidecars and add mTLS and auth to each. This keeps 7 services, the SQL coupling and the sync hops, and auth does not stop agent code in the kernel container.
  - Give each sidecar its own schema, as microservices. There is no requirement for independent scaling, and the cost is large (MISSION §5.2, §12).
  - Rewrite everything in one language. This is not justified (MISSION §5.3).
- **Consequences:**
  - The default stack goes from 10 containers to 6.
  - Most of `koda/internal_rpc` (about 8.3k lines) and about 10k lines of Rust go, and the grpcio and protobuf footprint shrinks.
  - Python must own the SQL before each fold.
  - The release bundle and installer change (M5-E5-T9).
  - The process-boundary test is the gate for any new service.

## ADR-002 — Agent-native tool governance (Option C)

- **Status:** accepted. The operator approved Option C on 2026-11-14 (EXECUTION_STATUS.md). The detailed design is in progress in `docs/engineering/adr/ADR-agent-native-tool-governance.md` (M1-E2-T1). Sequencing note (revision 1): the first confinement task (M1-E2-T4) covers the environment and working-directory allowlist only; network limits wait for a concrete kernel mechanism, and R-01 records that residual. The decision itself is unchanged.
- **Context:**
  - Provider CLIs run with every native tool enabled and approvals off: Claude with `bypassPermissions` and no tool lists, even for supervised agents; Codex with `danger-full-access` and `approval_policy=never`; Gemini with `yolo`.
  - Koda's policy gate, approval broker and command guard therefore govern only `<agent_cmd>` calls (D-002, F-GOV-10).
  - Workers run in `runtime-kernel`, whose isolation is cgroup limits only. They mount the `koda-state` volume that holds `.master.key`, and they receive the Postgres DSN and the S3 secret (D-047).
  - A prompt injection could plausibly read the key and decrypt every secret. This is code-verified, not proven at runtime.
- **Decision:** both options, in order.
  - **(A) Governed by default.** Provider permission modes are derived from the agent's Koda execution policy. Native autonomy is an explicit, audited, per-agent opt-in. Supervised agents never bypass.
  - **(B) Confinement.** The master key moves off the worker volumes. Provider CLIs get an environment allowlist with no DSN or S3 secret, network limits where supported, and a scoped Postgres role for workers.
- **Alternatives considered:**
  - (A) alone: secrets stay reachable by native tools when an agent opts in.
  - (B) alone: Koda's approvals still do not cover native tools.
  - Status quo plus documentation of an assumed external sandbox: leaves the critical risk open.
- **Consequences:**
  - Agents that rely on native shell or edit lose them until opted in. The operator accepted this impact.
  - Moving the key on existing installs (M1-E2-T3) and adding the database role (M1-E2-T5) each need their own §13 sign-off, because they touch production secrets and credentials.
  - Native-tool coverage becomes part of the guardrail test suite.

## ADR-003 — Loopback-by-default network exposure

- **Status:** accepted. The operator approved it on 2026-11-14. Implemented as NET-LOOPBACK (`307349e`, `52ffc26`). It passed two independent review rounds, and the local evidence is in VALIDATION_REPORT.md. M1-E1-T1 stays `in-review` until a GitHub Actions docker-smoke run is recorded.
- **Context:** the base compose file, the release bundle installed by the npm CLI and the production overlay all publish 8090 (control-plane API) and 3000 (dashboard) on every interface. The prod overlay appends ports instead of replacing them. The docs promise loopback behind a reverse proxy (D-044, D-045, D-007, D-034).
- **Decision:**
  - The control-plane API always binds `127.0.0.1`.
  - The dashboard binds `${WEB_PUBLISH_ADDRESS:-127.0.0.1}`, with an explicit opt-in for LAN access.
  - The prod overlay uses `!override`.
  - Rendered-config tests (`tests/test_compose_port_exposure.py`) guard every compose file.
- **Alternatives considered:** keep the public binds and fix the docs; rely on firewall guidance. Both leave the backend auth as the only barrier on a published port.
- **Consequences:**
  - Opening `http://<host>:3000` directly now needs a reverse proxy or the opt-in.
  - The container always listens on 8090, and `CONTROL_PLANE_PUBLIC_PORT` carries the host port for the OAuth relay URL.
  - The install, hardening and observability docs were updated. Plain HTTP over a LAN or tailnet still drops `Secure` cookies (M1-E1-T7).
  - The trusted-proxy rate limiting (M1-E1-T2) assumes this topology.
  - Open follow-up: the cluster overlay's `replicas: 3` with a fixed host port (ADR-022; M5-E6-T9 or M5-E6-T13 per Q-1).

## ADR-004 — One migration registry and runner

- **Status:** accepted (2026-11-14, Principal Architect). Amended by ADR-028: index builds and large backfills use a second, non-transactional migration kind.
- **Context:**
  - 50+ forward-only migrations live as Python strings inside `KnowledgeV2PostgresBackend`, the schema owner for about 130 tables.
  - The approval stores and the Rust artifact engine run DDL at runtime, the latter under an ACCESS EXCLUSIVE lock on every request.
  - Every process bootstraps the schema concurrently, statement by statement, under an in-process lock only.
  - The CI migrations gate is tautological.
  - See TD-005, TD-006, D-100, D-106, D-113.
- **Decision:**
  - Numbered SQL files in `koda/state/migrations/`, tracked in `schema_migrations`, with one runner.
  - Each migration runs in one transaction under `pg_advisory_xact_lock`.
  - Only the control plane and `koda migrate` apply DDL; workers wait for the current version.
  - No DDL exists outside that directory, enforced by a CI check.
  - The CI gate diffs the previous release's schema plus the new migrations against a fresh install.
  - Migrations stay forward-only. Rollback means restoring the backup that `koda update` takes (M2-E6-T2, formerly M7-E2-T2).
- **Alternatives considered:**
  - Alembic: adds a dependency and a model layer that the plain SQL files do not need.
  - Keep the inline registry and only add the lock: leaves app-wide schema ownership inside a knowledge module.
- **Consequences:**
  - The move must be behaviour-neutral, proven by a byte-identical schema dump (M5-E1-T1).
  - The Rust services still read the schema without owning it, so contract tests stay until they are folded (ADR-001).

## ADR-005 — One execution intake; strangler split of `queue_manager`

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:**
  - `queue_manager.py` is 9,438 lines and holds three functions of about 1k lines each.
  - Nine enqueue variants repeat the create, put, track, persist and spawn steps, with inconsistent checks, and pass options as raw dicts with underscore flags.
  - Tests always patch out `_execute_single_task` (TD-010, TD-011, D-021).
- **Decision:**
  - Every intake path (Telegram, dashboard, scheduler, squads, retries, child runs) calls `submit(TaskRequest)`.
  - Code moves into `koda/execution/{intake,worker,context,provider_executor,agent_loop,delivery,hooks}.py`. Each move is behaviour-neutral and keeps re-exports until callers migrate.
  - Behaviour is fixed after the move, not during it.
  - Post-turn work (squads, memory extraction, cost) attaches through a hook registry, so `execution` imports no squad internals.
- **Alternatives considered:** a rewrite of the queue, which is high-risk with today's test coverage; leaving it as is, where every M3 defect fix keeps landing in one file.
- **Consequences:**
  - M0-E3-T2 (real-Postgres characterisation tests) is a hard prerequisite.
  - Edits to `queue_manager.py` are serialised (MASTER_PLAN §8).
  - Defect fixes in M3 land before the move, so that the move is purely mechanical.

## ADR-006 — One retry and error policy; working circuit breakers

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:**
  - Retries happen in four layers: tenacity in the Claude adapter, stream-to-fallback, the provider chain and the task level. That is up to about 12 CLI runs per message.
  - Keyword heuristics in PT-BR and English turn some errors into successes.
  - Task retries replay side-effecting tools.
  - The breakers are checked with a check-then-skip pattern, so they never reach half-open and stay open forever.
  - See TD-020, D-179, D-051, D-020.
- **Decision:**
  - Adapters return a typed `ProviderError(kind, retryable)`.
  - The provider executor owns the single retry and fallback policy.
  - A run that has executed a write tool is never replayed at task level.
  - tenacity is removed.
  - Breakers are uniform per provider, with a working half-open probe.
- **Alternatives considered:** tenacity everywhere, which adds one more layer instead of removing three; removing the breakers, which loses fast failure during provider outages.
- **Consequences:**
  - Retry counts change; this is documented in the changelog.
  - Fewer duplicate provider runs and lower cost.
  - Error classification becomes unit-testable.

## ADR-007 — One tool catalog

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:**
  - Five parallel catalogs (`_WRITE_TOOLS` / `_READ_TOOLS` / `_TOOL_HANDLERS`, `tool_prompt`, `CORE_TOOL_CATALOG`, `tool_registry`) have measurably drifted: 26 handlers are missing.
  - Unknown tools are treated as read-only by the gates.
  - `request_skill` is read in one place and write in another (TD-030, D-132).
- **Decision:**
  - `koda/tools/catalog.py` holds one `ToolSpec` per tool: handler, read or write, category, policy resource.
  - The dispatcher, the prompt builder, policy and the UI all derive from it.
  - An unknown tool is a write tool.
- **Alternatives considered:** keep the drift detector, which detects drift but does not prevent it; generate the catalogs from the dispatcher, which keeps the derived lists.
- **Consequences:**
  - Adding a tool takes one declaration.
  - The CLAUDE.md rule "keep tool_prompt and tool_dispatcher aligned" becomes structural, and the guide is updated in M10-E1-T2.

## ADR-008 — One execution-policy evaluator

- **Status:** proposed. The authoritative switch, the policy-store migration and the retirement of legacy routes wait on Q-5 and §13 approval. Step 1 is amended by ADR-039: one engine with fnmatch for every rule, with the replay safeguard moved to delivery (AG-09, AG-10).
- **Context:**
  - Two evaluators, `services/execution_policy.py` and `control_plane/execution_policy.py`, give different decisions for the same validated policy (verified).
  - Example: a validated deny `mcp_*__delete_*` is ignored at runtime.
  - Eight policy stores overlap, three of which are already labelled legacy, and the legacy path is still the default (TD-031, TD-069, D-024).
- **Decision (proposed):**
  1. Interim parity, fail-safe only (M1-E4-T9; accepted): a deny rule applies when either today's runtime matcher or fnmatch matches, so a deny can only match more calls; allow rules keep today's runtime semantics, and validation rejects new allow patterns whose meaning differs between the matchers; simulate calls the runtime evaluator. A replay of every stored policy under both semantics must show no allow decision widening, or the task stops and the case goes to Q-5.
  2. An offline replay of the stored policies, the shared vectors and the recorded audit decisions through both evaluators produces the difference report for Q-5 (M5-E3-T2). No dual-path code runs in production.
  3. Make one evaluator authoritative, by default the runtime one, chosen on the replay evidence, and delete the other (M5-E3-T3).
  4. Migrate the other policy stores into the execution policy, one store per task, each with a before-and-after effective-permission report (M5-E3-T5, M5-E3-T12 to T17). Rules may only tighten unless the operator approves a difference (REFERENCE_RESEARCH P16).
  5. Each store task deprecates that store's legacy routes for one release (ADR-030), and M5-E3-T19 removes them after the window. Legacy routes that carry no permissions are retired separately (M5-E6-T8).
- **Alternatives considered:**
  - Make the control-plane evaluator, with fnmatch semantics, authoritative. Viable; decided by the replay report.
  - Keep both with shared test vectors. Drift continues.
  - Evaluate both engines on every production decision with diff logging. It gives the same report as the offline replay, at the cost of dual-path runtime code and a soak run.
  - Switch the runtime matcher to fnmatch for allow rules too as the interim step. Rejected: interior wildcards in allow rules would start matching, which widens permissions without approval.
- **Consequences:** effective permissions may change. That is why steps 3 to 5 need operator approval with the report attached.

## ADR-009 — One approval pipeline, persisted in Postgres

- **Status:** accepted (2026-11-14, Principal Architect). Fixing D-011 (M3-E3-T1) makes policy-approved shell, git and supervised writes run for the first time, which widens what agents can do, so that task is `needs-approval` and depends on the git, background-shell and path fixes (MASTER_PLAN M3-E3-T1).
- **Context:** five stacked gates encode the same intent and contradict each other: policy, the `_execution_approved` contextvar, a supervised check, dry-run and an `_approved` flag. As a result:
  - the contextvar is never set in the queue worker, so policy-approved shell, git and supervised writes always fail (D-011, hidden by a global test fixture);
  - pending approvals live in worker memory, so the dashboard in the supervisor cannot see them (D-012);
  - restored pending operations crash (D-163);
  - grant writes wipe other agents' grants, and INTEGER ids overflow (D-059, D-060).
- **Decision:**
  - The flow is decision, then request, then a fingerprinted grant, then execute.
  - Requests and grants live in registry tables with BIGINT ids and agent scope, and cross processes through LISTEN/NOTIFY.
  - Only grants persist. Pending requests expire on restart.
  - The verbs are the same on Telegram and the dashboard: allow once, allow scope, deny with a reason. The card shows the exact scope (REFERENCE_RESEARCH P15).
- **Alternatives considered:**
  - Proxy the dashboard approval routes to the worker runtime API. This keeps the state in memory, which is lost on restart, and keeps two sources of truth.
  - Keep the contextvar and set it in the worker. This fixes D-011 but leaves five gates.
- **Consequences:**
  - Dashboard approvals work, and restart semantics are explicit.
  - The global approval test fixture goes (ADR-027).
  - The JSON fallbacks are retired after a one-time import (M2-E1-T2).

## ADR-010 — Security primitives in process, one of each

- **Status:** accepted (2026-11-14, Principal Architect). ADR-033 proposes to supersede the command-guard clause (one Python guard in the worker) with the kernel's guard as the only one. ADR-034 confirms the MCP client stays on the aiohttp stack.
- **Context:**
  - A shell command is checked against the denylist up to four times, and the check is still easy to bypass.
  - There are four safe-path resolvers (`/cat .env` works while `file_read` refuses) and three redactors.
  - There are two HTTP stacks with different SSRF and redirect semantics, and the urllib paths have no private-IP check.
  - The security sidecar is a synchronous gRPC hop on every LLM subprocess env build, shell command and redaction.
  - See TD-032, TD-033, TD-056, TD-113, D-003, D-066.
- **Decision:**
  - `koda/security/` holds one command guard, one path resolver relative to `work_dir`, one redactor and one SSRF guard, with a pinned resolver and IPv4-mapped normalisation.
  - aiohttp is the single HTTP stack.
  - The kernel keeps its linked `koda-security-core` check only for commands it runs itself.
  - The command guard is documented as a guard, not a sandbox. Containment comes from ADR-002 and from the container.
- **Alternatives considered:** make the Rust service the single implementation, which keeps a network hop for pure functions and an availability dependency; ship the PyO3 guard, which was never shipped.
- **Consequences:**
  - The security container is removed (M5-E5-T1), with the Rust tests kept as parity vectors.
  - pytest no longer needs cargo to start a guard.

## ADR-011 — Cross-process state only through Postgres or the worker runtime API

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:** several things are assumed shared but live in one process's memory:
  - pending approvals;
  - the memory recall cache;
  - the in-memory squad bus, the default, useless with one process per agent;
  - kernel environment state.

  In addition, the web and backend keep two public-path lists that have already drifted (ARCHITECTURE_AUDIT §5.5), and one LISTEN/NOTIFY listener does not reconnect (D-167).
- **Decision:**
  - The control plane never reads worker memory.
  - Shared state is Postgres rows, with NOTIFY where latency matters, or calls to the worker runtime HTTP API.
  - There is one reconnecting LISTEN implementation.
  - Squads refuse to start on the in-memory bus.
  - One public-path list is tested against both tiers.
- **Alternatives considered:** Redis or a message broker. This adds infrastructure without a measured need (MISSION §12).
- **Consequences:** a few cross-process paths gain the latency of a database round trip, and behaviour becomes consistent across restarts and processes.

## ADR-012 — Async repositories replace the sync bridge on hot paths

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:**
  - About 226 `run_coro_sync` call sites block event loops for up to 30 s per call, in both the supervisor and the workers.
  - Combined with sequential PTB update processing and handlers that hold the per-user lock, this can stall the whole bot.
  - The squad stack opens 10 extra pools.
  - Per-call codec installation drops the statement cache.
  - See D-111, D-110, D-076, TD-004, TD-098.
- **Decision:** convert incrementally:
  - `asyncio.to_thread` as an interim step for control-plane handlers;
  - awaitable repositories on the queue hot path after `submit()` lands;
  - sync wrappers only for the CLI;
  - one pool per process, with codecs installed in the pool `init` hook.
- **Alternatives considered:** a big-bang async conversion, with high ordering and concurrency risk; thread offloading everywhere, which hides the problem and adds contention.
- **Consequences:**
  - Each conversion keeps per-user FIFO ordering and is proven by the characterisation tests.
  - A loop-lag probe becomes part of the performance baseline (M9-E4-T1).

## ADR-013 — One configuration surface, enforced in CI

- **Status:** accepted (2026-11-14, Principal Architect). ADR-036 supersedes the key-registry, classification, generated-reference and registry-check clauses; the rest stands.
- **Context:**
  - `koda/config.py` reads about 381 to 387 env keys into import-time constants, and about 606 env reads exist repo-wide.
  - Three other settings modules exist and diverge, with two dotenv load points.
  - Test fixtures patch every module that copied a constant.
  - Dead knobs, Neo4j among them, are exposed to operators.
  - CLAUDE.md requires settings to be centralised (TD-001, TD-002, TD-003, D-149).
- **Decision:**
  - One `koda/config` package with one dotenv load.
  - A key registry classifies every key as an operator knob, publish-time plumbing or dead.
  - `docs/config/reference.md` is generated from the registry.
  - CI rejects `os.environ` reads outside config and keys missing from the registry.
  - A typed `Settings` object is introduced slice by slice, starting with DSNs and paths.
  - A direct launch reloads config after env hydration (Q-19).
- **Alternatives considered:** pydantic-settings, which is acceptable if validation needs grow but is not added up front; stdlib dataclasses come first (MISSION §12).
- **Consequences:** `.env.example` and the reference doc are checked against the registry, dead keys are deleted (M4-E1-T2), and tests construct `Settings`.

## ADR-014 — Memory in Python SQL with Postgres full-text search

- **Status:** proposed. Acceptance requires the spec tests and the one-off comparison in M5-E5-T3 (Q-7). Defect fixes on the current engine (M3-E4) proceed regardless, but are kept to the minimum the journeys need, because the engine is removed afterwards.
- **Context:**
  - The Rust memory engine is about 3.5k lines, roughly 90% of them dashboard projections.
  - Recall scores at most 400 recent rows lexically.
  - Two writers write `napkin_log`. The Deduplicate RPC is a no-op that writes still depend on. Recall is hard-filtered to the in-flight task.
  - Rust and Python scorers run in series with inconsistent source names, and neither is tested on real data.
  - See D-013, D-070, D-071, D-092, TD-082, TD-083, TD-084, TD-094.
- **Decision (proposed):**
  1. Fix the defects on the current path first, with the smallest Rust change that makes the journeys pass (no proto changes).
  2. Port recall directly to Python with tsvector and GIN candidate selection and one scorer, using the M0-E3-T5 and M3-E4 tests as the specification. No runtime backend flag (M5-E5-T3).
  3. Before merging, run a one-off comparison on a seeded corpus of 10,000 rows: at least 80% top-5 overlap with the Rust engine on queries with lexical overlap, every miss explained by a fixed defect, and p95 latency no worse than the Rust p95 plus 20 ms.
  4. Move the curation and map projections to Python with one `napkin_log` writer, checked by identical API snapshots on a seeded copy (M5-E5-T4).
  5. Remove the engine and its container (M5-E5-T10). Rollback is the previous release, which still runs the engine and works against the migrated schema because the full-text column and index are additive.
- **Alternatives considered:**
  - Keep the Rust engine as the single scorer and writer, and remove the Python duplicates. This keeps a sidecar but is the fallback if parity fails.
  - pgvector embeddings for memory. There is no embedding producer today.
- **Consequences:** if accepted, one sidecar and one gRPC contract go. If the comparison fails, this ADR is superseded by "keep Rust as the single memory implementation". A runtime flag with a dual path and a standing parity report was considered and rejected: the scorer looks at no more than 400 rows, and the characterisation tests are a sufficient specification.

## ADR-015 — Knowledge v2 scope

- **Status:** proposed, blocked on Q-6. Removal is a §13 decision.
- **Context:**
  - In PRIMARY mode, the default and the only working mode, nothing writes `knowledge_chunks`, embeddings, entities or relations. Operator assets, runbooks and workspace docs are never retrieved (D-014, TD-087).
  - The Rust retrieval engine is well tested over empty tables.
  - The grounding gate may force `needs_review` as a result (unverified).
  - The configured vector dimension is 1024, but the default embedding model is 384 (D-152).
  - sentence-transformers is not installed in the images.
- **Options:**
  - **(A) In scope.** One Python ingestion service upserts control-plane assets, approved runbooks and workspace docs. pgvector retrieval is ported from Rust, with its tests as the spec. One embedding model and dimension, declared as a dependency or an extra.
  - **(B) Out of scope.** Remove the write side, the assets UI, the knowledge graph, the retrieval engine and the per-query embeddings.
- **Accepted interim, whichever option wins:**
  - the grounding gate skips when the corpus is empty (M6-E1-T5);
  - the dead local and OFF paths and the storage-mode wrappers are removed (M4-E1-T6);
  - the knowledge assets UI is labelled "Not available yet" (M6-E1-T10).
- **Carrying it out:** M6-E1-T4 records the outcome and opens one task per outcome step (A1, A2 or B1, B2), each with its own acceptance criteria. The former M5-E5-T5 is replaced by those tasks.
- **Consequences:** (A) adds a real feature and an embedding dependency. (B) removes about 12k lines and a sidecar, and changes the advertised feature set (README).

## ADR-016 — Squads: keep the core, consolidate the plumbing

- **Status:** accepted (2026-11-14, Principal Architect). Whether squads are on by default stays a product decision (Q-9). ADR-032 writes down the orchestration semantics this plumbing serves.
- **Context:**
  - The squad core is coherent: Postgres threads, tasks with CAS claims, bounded reply obligations and the access service.
  - Around it, the routing pipeline is duplicated between Telegram and the web, and dispatch tries three transports.
  - About 3k squad lines sit in `queue_manager`, `tool_dispatcher` and `api.py`, and the squad stack opens 10 extra pools.
  - The `agent_comm` category bundles admin operations, delegation limits reset on every hop, post-processing deadlocks, and budget pause is advisory.
  - See TD-097, TD-104, TD-098, TD-111, D-019, D-038, D-095, D-096, D-075.
- **Decision:**
  - Keep the core.
  - One `route_inbound()`.
  - One durable dispatch: a Postgres row plus NOTIFY to the target worker's inbox, with no in-process execution of another agent's turn.
  - A post-turn hook (ADR-005).
  - A `squad_admin` category with caller authorization.
  - The delegation chain and hop limits are carried and enforced in the dispatcher, with thread status and budget gates.
  - The router runs as a singleton through an advisory lock.
- **Alternatives considered:** remove squads, an advertised capability; keep three transports and add idempotency keys, which keeps unclear delivery semantics.
- **Consequences:** squad delivery becomes reasoned about in one place, and uncontrolled loops are bounded (R-27). Each squad agent's turn runs in that agent's own worker, with its own spec and secrets.

## ADR-017 — Channels: Telegram is the only live channel

- **Status:** proposed. Q-2 (Telegram optional per agent) and Q-3 (non-Telegram channels) are open.
- **Context:**
  - Every agent must be a Telegram bot: publish fails without `AGENT_TOKEN`, and the worker is a PTB application (D-124).
  - Eight adapters are never started, yet the dashboard validates their credentials and shows "connected" (D-017).
  - The web tier pulls decrypted channel secrets in order to validate them (D-170).
  - The bot-gateway duplicates PTB polling and acks updates that failed (D-098).
- **Decision (proposed):**
  - Telegram is the only live channel.
  - Non-Telegram channels are shown as "Not available" now; this is reversible (M6-E1-T2, ready).
  - The adapters, extras and forms are removed unless the operator wants them wired (M6-E1-T3, approval).
  - Telegram becomes optional per agent, with runtime-HTTP-only workers (M3-E5-T3, formerly M6-E1-T1; Q-2 is in approval batch 1 because J-11 is a broken critical journey).
  - Channel validation moves to the backend regardless (M5-E8-T5, accepted).
  - Bot-gateway removal falls under ADR-001 and Q-22.
- **Alternatives considered:** wire `ChannelManager` into the workers, which needs tests and upkeep for 8 adapters with 0% coverage today.
- **Consequences:** the UI stops claiming capabilities that do not work (MISSION §6.3). Dashboard-only agents become possible if Q-2 is approved.

## ADR-018 — Deletion policy

- **Status:** accepted (2026-11-14, Principal Architect). ADR-037 clarifies how the classes apply to configuration keys, bundled behaviour changes and interim labels.
- **Context:**
  - About 12k unreachable web lines, about 20 dead Python clusters, a never-shipped crate, dead scripts and accidental root files (SYSTEM_INVENTORY §7, TECHNICAL_DEBT simplification ranking).
  - MISSION §10 forbids removing working functionality without a documented and validated replacement or deprecation. §13 requires approval to remove major user-facing functionality.
- **Decision:** three classes.
  1. **No runtime consumer**, proven by grep and the import graph. Delete together with its tests in a deletion-only change, reviewed by REV.
  2. **Present but never functional.** First disable it or label it "Not available" (reversible). If it is user-facing or documented, delete it only after approval.
  3. **Working or documented user-facing.** `needs-approval`, with an impact analysis.

  A CI reachability check stops unreachable web modules from coming back.
- **Alternatives considered:** keep dead code "for later", against MISSION §12; delete aggressively, against MISSION §10 and §13.
- **Consequences:** deletion work (M4) mostly runs early and in parallel, because it shrinks the surface that later refactors touch. Coverage figures drop where tests only covered dead code, and this is expected.

## ADR-019 — One error envelope; OpenAPI as the contract source

- **Status:** accepted (2026-11-14, Principal Architect). ADR-030 adds a one-release compatibility window before the final envelope shape.
- **Context:**
  - About 140 string error envelopes coexist with 15 structured ones.
  - A blanket KeyError→404 and ValueError→400 mapping masks bugs and leaks internals.
  - The web shows "[object Object]".
  - 217 of 304 OpenAPI operations have generic responses, and the TypeScript types are hand-mirrored and have drifted three times.
  - See TD-075, D-135, D-212, F-PLT-14.
- **Decision:**
  - Every error is `{"error": {"code", "message", "user_action?"}}`, raised as typed domain errors.
  - The routes the web uses get real response schemas, and the TypeScript types are generated from them.
  - A CI contract test runs across the route matrix.
- **Alternatives considered:** RFC 9457 `application/problem+json`. It is equally valid, but the existing structured shape, already used by 15 routes, minimises churn.
- **Consequences:** the error body changes for external API clients, which is noted in the changelog (M10-E1-T3). Contract drift becomes a CI failure instead of a runtime bug.

## ADR-020 — Web data layer and outage semantics

- **Status:** accepted (2026-11-14, Principal Architect). This adopts the Q-15 default.
- **Context:** the web app has:
  - seven or more fetch helpers and three error parsers, which handle 401, abort and unavailable states differently;
  - three cache policies and four SSE reconnect loops;
  - navigation metadata defined in three places;
  - a BFF that turns upstream failures into synthetic HTTP 200 payloads, so outages look like empty data or $0 costs.

  See TD-146, TD-154, TD-159, TD-130, TD-150, D-101.
- **Decision:**
  - One HTTP client and error parser that match ADR-019.
  - React Query tiers only.
  - One SSE hook with bounded backoff.
  - One route registry for the sidebar, the topbar, the palette and titles.
  - On an upstream failure the BFF returns 503, and the shell shows one degraded-mode banner.
  - Unreachable code is removed first (ADR-018).
- **Alternatives considered:** keep the synthetic payloads, which hide outages and violate MISSION §6.3.
- **Consequences:** every page must render the unavailable state, which is tested. The BFF boundary is kept as a strength (ARCHITECTURE_AUDIT §4).

## ADR-021 — Delivery consolidation

- **Status:** accepted (2026-11-14, Principal Architect). Changing the compose project name for packaged installs is excluded and needs approval (M7-E2-T3).
- **Context:** delivery has:
  - two Python images of about 6 GB each with the same contents;
  - six near-identical Rust Dockerfiles, each building the whole workspace;
  - a hand-maintained release compose file that has drifted, checked only by string tests;
  - unpinned provider CLIs, floating base-image tags and action tags;
  - a `release.yml` that re-implements the PR and security workflows (about 600 lines);
  - three SCA layers per ecosystem.

  See TD-123, TD-171, TD-172, TD-177, TD-170, TD-174, D-046.
- **Decision:**
  - One Python image for `app` and `runtime-kernel`, with the kernel binary from one cached Rust stage.
  - The release compose file is generated from the base file plus an override, guarded by rendered-config tests.
  - Provider CLIs are pinned, actions are pinned by SHA and images by digest, there is a `rust-toolchain.toml`, and CI uses the images' Node major.
  - The release workflow reuses the PR and security workflows through `workflow_call`.
  - One SCA tool per ecosystem, plus CodeQL, gitleaks and Trivy on every shipped image.
- **Alternatives considered:** keep the duplicated pipelines, which means slow builds and drift; per-service images, which adds no value once ADR-001 lands.
- **Consequences:** builds, scans and pulls get faster, and drift is impossible by construction. Dropping Snyk, if chosen, removes a possible paid dependency, which needs no approval because it reduces cost.

## ADR-022 — Single-host deployment

- **Status:** proposed (Q-1). Removing cluster mode is a §13 decision.
- **Context:**
  - A multi-worker lease and janitor protocol protects a queue that only one process can ever hold. Lease loss and janitor requeues are not acted on (TD-016, D-089).
  - Cluster mode (leader election, placement, drain) targets fleets of 100+ agents in a single-owner product.
  - Its endpoints are unauthenticated (D-033), and its overlay gives every replica the same supervisor id (D-082).
- **Decision (proposed):**
  - Until Q-1 is decided: fix the lease gaps (M5-E2-T9) and authenticate `/cluster/*` (M1-E1-T15). Both are accepted interim work.
  - On approval: remove cluster mode (M5-E6-T9), and replace the lease protocol with startup recovery plus guarded status transitions (M5-E2-T10).
  - If Q-1 keeps cluster mode instead: M5-E6-T13 gives each replica its own supervisor id and stops every replica publishing the same host port.
- **Alternatives considered:** keep cluster mode and finish it, with unique ids, auth, tests and CI for the overlay.
- **Consequences:** if approved, several thousand lines and an overlay go, and multi-host deployments become unsupported.

## ADR-023 — Agent deletion semantics

- **Status:** proposed (Q-11). The destructive part is a §13 decision.
- **Context:**
  - Hard delete leaves `cp_secret_values` and about 12 other per-agent tables orphaned. Recreating an agent with the same id inherits the old encrypted token and secrets (D-054).
  - `archive_agent` exists but is unused.
  - Only 7 foreign keys exist across about 130 tables.
- **Decision (proposed):**
  - A canonical per-agent table list with a schema-completeness test (M2-E3-T2; accepted, no behaviour change).
  - Archive becomes the default action.
  - Hard delete purges every listed table, secrets included, in one transaction (M2-E3-T3, approval). The approval request cites a restore drill (ADR-029).
- **Alternatives considered:** foreign-key cascades. These need the typed-schema work in M5-E1-T5, which needs its own approval, so they are deferred.
- **Consequences:** no orphaned secrets, and deletion becomes reversible by default.

## ADR-024 — Data retention and privacy

- **Status:** proposed. Every destructive step is a §13 decision.
- **Context:**
  - The daily purge targets tables that do not exist, and `AUDIT_RETENTION_DAYS` has no effect (D-053).
  - `runtime_*` tables are never purged (D-112).
  - `/forget` only deactivates rows, and redacted previews remain in `memory_recall_audit` (D-036).
  - Secret previews are stored but never read (TD-077).
- **Decision (proposed):**
  - One retention job, in report-only mode now (M2-E5-T1, accepted). It deletes in batches once the operator approves the defaults (M2-E5-T2).
  - `/forget` hard-deletes, and stored secret previews are purged (M2-E5-T3).
  - The first purge on an install refuses to run without a backup less than 24 hours old, and every approval request cites a restore drill (ADR-029, M2-E6-T1).
- **Alternatives considered:** keep soft deletion and disclose it in the UI. This fails the privacy expectation that "forget" sets.
- **Consequences:** table growth is bounded and privacy behaviour matches the words used. Deleted data is unrecoverable outside backups.

## ADR-025 — Signing-key separation and secret references in snapshots

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:**
  - The Fernet master key is reused as the HMAC signing key (TD-078).
  - Published agent snapshots embed secret ciphertext, so rotating a secret needs a republish (ARCHITECTURE_AUDIT §3.3, §8.7).
- **Decision:**
  - Derive the signing key with HKDF and a distinct label (M1-E6-T3). Runtime tokens last 300 s, so the cut-over is transparent.
  - Snapshots reference secrets by id, and workers resolve them at start (M5-E6-T7).
- **Alternatives considered:** a separate signing-key file, which means one more secret to back up with no added separation; keeping ciphertext in snapshots, which keeps rotation coupled to publishing.
- **Consequences:** the key material is unchanged, so no data migration is needed. Secret rotation stops requiring a publish.

## ADR-026 — Master-key relocation and rotation

- **Status:** proposed. Both steps are §13 decisions (production secrets). Option C (ADR-002) approved the direction.
- **Context:**
  - The master key sits on the `koda-state` volume, which the runtime-kernel and every agent worker also mount (D-047).
  - `rotate_master_key` has no production caller, and there is no backup tooling (TD-078, D-172).
  - Losing the key makes every stored secret unrecoverable.
- **Decision (proposed):**
  - Move the key to an app-only volume, through an installer migration that copies, verifies a decrypt, and only then removes the old copy (M1-E2-T3).
  - An operator rotation command re-encrypts every secret, with a verified backup of the old key (M5-E6-T11, formerly M1-E6-T4; it waits on secret references in snapshots, M5-E6-T7).
  - Backups always include the key, and the restore is drilled in CI before either step is requested (M2-E6-T1, formerly M7-E2-T1; ADR-029).
- **Alternatives considered:** leave the key in place and rely on confinement alone (ADR-002 B), which leaves a single filesystem control between agent code and every secret; an external KMS, which adds infrastructure and possibly cost.
- **Consequences:** the key is no longer reachable from worker filesystems. An interrupted migration or rotation must be recoverable, so the rollback is tested before approval.

## ADR-027 — Test strategy for the consolidation

- **Status:** accepted (2026-11-14, Principal Architect).
- **Context:**
  - 212 of 324 test files mock, with 2,145 `patch(` calls.
  - No test executes `_execute_single_task`.
  - An autouse fixture grants execution approval globally and hides D-011.
  - The Postgres suite only recently became runnable, and its CI job has not run.
  - The Playwright suite runs nowhere, and web tests are not type-checked.
  - Infrastructure invariants are tested by string matching.
  - The coverage gate is 53.5% against a measured 61%.
  - Concurrent runs share a security-guard port.
  - See D-021, TD-041, D-107, D-108, D-129, TD-186, TD-189, D-175.
- **Decision:**
  - Before any refactor, add characterisation tests on real Postgres, with a stub provider only at the adapter boundary.
  - Known defects are encoded as `xfail(strict=True)` and flipped by the fixing task.
  - No global fixture grants approval.
  - Postgres CI fails on unexpected skips.
  - Playwright smoke runs in docker-smoke.
  - Rendered-config tests replace string tests.
  - The coverage gate is ratcheted to the measured value.
  - Strict markers are on, and every test session gets its own guard port and database.
  - Mocked provider tests are never presented as proof that real providers work (MISSION §7.6).
- **Alternatives considered:** refactor first and test afterwards, which risks undetected behaviour change (R-08); a full end-to-end suite only, which this environment cannot run (no Docker or credentials).
- **Consequences:** M0 must finish its characterisation tasks before the large M5 moves. Some tests get slower but cover the real path.

## ADR-028 — Online migrations and a lock budget

- **Status:** accepted (2026-11-14, Principal Architect). Amends ADR-004's clause that every migration runs in one transaction.
- **Context:**
  - ADR-004 runs each migration in one transaction under `pg_advisory_xact_lock`.
  - Several planned migrations build indexes or rewrite large tables on existing installs: the casing indexes (M2-E3-T5), the full-text index on `napkin_log` (M5-E5-T3), the base-importance backfill (M3-E4-T4), the typed columns (M5-E1-T5), the BIGINT widening (M5-E1-T6) and the hot-query indexes (M9-E1-T7).
  - `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. A plain `CREATE INDEX` blocks writes for the whole build, and a long rewrite holds an exclusive lock, so agents on hot tables would stall during an upgrade.
- **Decision:**
  - **Transactional kind (default).** One transaction under `pg_advisory_xact_lock`, with `SET LOCAL lock_timeout` equal to the lock budget (default 5 s, a named constant). A migration that cannot take its locks in time fails cleanly and is retried at the next start.
  - **Online kind.** Used for `CREATE INDEX CONCURRENTLY` and batched backfills. It runs under a session-level advisory lock, one statement at a time. Each statement is idempotent (`IF NOT EXISTS`, and an `INVALID` index left by a failed build is dropped and rebuilt). Each backfill batch commits within the lock budget. The migration is recorded as applied only after every statement succeeds.
  - The migrations gate (M2-E2-T5) rejects a transactional index build on a table it lists as large.
  - The runner test seeds a table of 1 million rows and checks that a concurrent writer is never blocked longer than the budget.
- **Alternatives considered:**
  - Document manual index builds for operators to run out of band. Operators forget, and schemas drift.
  - Accept write blocking during upgrades. Hot tables such as `napkin_log` and `query_history` would stall running agents.
  - An external tool such as pg_repack. It adds a dependency for a handful of migrations.
- **Consequences:** the runner has two tested paths. Online migrations are not atomic, so each must be safe to resume. Upgrades can take longer, but agents keep working while they run.

## ADR-029 — A proven restore precedes destructive or irreversible change

- **Status:** accepted (2026-11-14, Principal Architect). It makes the approval process stricter, which is within mission authority.
- **Context:**
  - The backup and restore runbook cannot be run as written (D-172), and recovery has never been tested (R-28). Losing the master key loses every secret (R-07). Both risks are Critical.
  - The first draft put the backup task in M7 (priority 5), while M1 and M2 tasks that move key material, rewrite rows or delete data said "with a backup step" without depending on a backup that had been shown to restore.
  - Mission §13 asks for a rollback approach for every high-risk change.
- **Decision:**
  - Backup and restore are scripted and drilled in CI in M2 (M2-E6-T1), before any destructive work.
  - Every destructive or irreversible task depends on M2-E6-T1: M1-E2-T3, M1-E2-T5, M1-E6-T1, M2-E3-T3, M2-E3-T5, M2-E5-T2, M2-E5-T3, M5-E1-T5, M5-E5-T7, M5-E6-T11 and M7-E2-T3.
  - Every approval request cites the latest restore drill, or states that none exists yet. A task that touches data, secrets or volumes on existing installs cannot start, whenever it was approved, until a drill no more than 30 days old is recorded in VALIDATION_REPORT.md.
  - `koda update` takes a backup before it migrates, and stops if the backup fails (M2-E6-T2). The new migration runner (M2-E2-T2) depends on it.
  - The first retention purge on an install refuses to run without a backup less than 24 hours old (M2-E5-T2).
- **Alternatives considered:**
  - Rely on the operator's own backups. Unverified, and nothing tells the operator when one is needed.
  - Document backup steps per task. Each would differ and none would be tested, which is how today's runbook drifted.
- **Consequences:**
  - Destructive work waits on CI evidence.
  - Backups contain the master key, so they are as sensitive as the key: mode 0600, and the runbook says so.
  - Backups use disk; M7-E5-T1 sets a retention count.

## ADR-030 — External contract changes: one-release window, changelog in the same change

- **Status:** accepted (2026-11-14, Principal Architect). Amends the consequences of ADR-019 and the mitigation of R-11.
- **Context:**
  - The plan changes several external contracts: the error body of about 140 routes, legacy route families, the 401 on failed login, the 409 on id collision, the 503 on outage, the `/health` payload, startup refusals, agent tool lists, Telegram commands and retry counts.
  - The first draft treated them inconsistently: retiring legacy routes was approval-gated with a one-release deprecation, while the error-body change had no window at all. The changelog was a fixed list in one late task, and it had already missed several changes.
  - The API consumers of a self-hosted, single-owner product are unknown (R-11).
- **Decision:**
  1. A change to an API response body, or the removal of a route, keeps the old shape or route for one release. That is a parallel field or a `Deprecation` header, followed by a separate task that removes it.
  2. Such changes are `Gate none`, unless they change permission semantics, in which case §13 applies.
  3. Every task that changes startup validation, an API body, a command, a tool list, retry behaviour or a compose default writes its own changelog entry in the same change, and lists `changelog entry` in its Tests field. M10-E1-T3 checks that every such done task has its entry.
  4. For the error envelope: for one release, every error keeps a top-level string `error` and adds `error_detail: {code, message, user_action?}` (M5-E6-T1). The next release moves to `{"error": {code, message, user_action?}}` (M5-E6-T12).
- **Alternatives considered:**
  - Version negotiation through a request header. More machinery for consumers nobody has identified.
  - Changelog only, with no window. Simpler, but it breaks any client on upgrade without notice.
  - Approval for every contract change. It would flood the operator with low-risk requests.
- **Consequences:** the envelope change and route retirement each take two tasks, and the web parser handles both shapes for one release.

## ADR-031 — Learning: definition and measurable behaviour

- **Status:** proposed. Accepted when M6-E4-T1 produces the measures on a seeded run.
- **Context:**
  - Mission §7.4 requires "learning" to have an explicit definition and measurable behaviour, and forbids silent training, uncontrolled self-modification and unrestricted propagation.
  - Koda has several learning-like paths, each partly broken:
    - memory extraction, whose recall is filtered to the in-flight task (D-013);
    - utility feedback, a no-op while recall is filtered (F-MEM-14);
    - knowledge candidates promoted to runbooks, whose steps never reach the prompt (F-MEM-22);
    - improvement proposals, whose "apply" only writes a ledger row (F-MON-24).
  - REFERENCE_RESEARCH P12 to P14 describe the target experience.
- **Decision (proposed):**
  - **Definition.** Learning in Koda is a durable, inspectable change to what an agent uses in later turns, made through one of four channels only:
    1. memories extracted from conversations;
    2. user or operator feedback on, and corrections of, those memories;
    3. runbook candidates that an operator promotes;
    4. improvement proposals that an operator accepts.
  - **Limits.** Nothing else changes behaviour. There is no model training, no silent prompt or policy self-modification, and no propagation across agents or users without an operator action.
  - **Measures, per agent:** recall hit rate (turns in which a recalled memory was used), the utility feedback ratio, operator corrections and deactivations, and promotions accepted versus rejected (M6-E4-T1).
  - **Control.** Every learned item shows its provenance and can be edited or deactivated (P14; M6-E4-T2). Hard deletion follows ADR-024.
  - **Queues.** Two review queues remain, memory review and proposals, until there is a measured need for one inbox (P13 deferred).
- **Alternatives considered:** one learning inbox now (P13), with no measured need; auto-applying proposals, which Q-16 rejected.
- **Consequences:** M3-E4-T7, M6-E4-T1 and M6-E4-T2 carry it out. F-MEM-22 and F-MON-24 stay labelled until Q-6 and typed proposal executors exist.

## ADR-032 — Squad orchestration semantics

- **Status:** proposed. Accepted when every rule below has a passing test (M3-E6-T7).
- **Context:**
  - Mission §7.2 asks for explicit orchestration semantics rather than ambiguous agent-to-agent behaviour.
  - ADR-016 consolidates the squad plumbing but does not state the rules.
  - Today the coordinator chooses per message between answering itself, delegating and handing off, and a synthesis gate exists (REFERENCE_RESEARCH P6).
- **Decision (proposed):**
  1. **Mode.** There is one mode, "lead synthesizes". The coordinator owns the thread. It answers itself, delegates tasks or hands off a turn, and when delegated tasks finish, synthesis gives the single final answer. A mode selector (P6) waits until a second mode has a user.
  2. **Context.** The thread transcript is shared by that thread's participants only. Each agent's spec, memory, secrets and tools stay its own. A delegated task carries an explicit goal and the transcript excerpt the coordinator chooses.
  3. **Ownership.** Each task has one owner through a compare-and-set claim, and reply obligations are bounded.
  4. **Conflict.** Synthesis attributes each contributing reply. Contradictory replies are both shown with attribution, and none is dropped silently.
  5. **Cancellation.** Cancelling a thread, or the coordinator's task, cancels its open squad tasks and their child runs (M3-E2-T4). Emergency stop covers every agent (M3-E2-T5).
  6. **Retries.** These follow ADR-006. An expired claim is redispatched once to the planned assignee, then escalated to the coordinator. Write tools are never replayed.
  7. **Limits.** Delegation depth and hop limits travel in request metadata (M3-E6-T4), and a paused or over-budget thread runs no new turns (M3-E6-T5).
  8. **Audit.** Each routing decision writes one routing record (M5-E7-T4).
- **Alternatives considered:**
  - Several coordination modes now. No user has asked for one.
  - Free agent-to-agent messaging without a coordinator. Loops are unbounded (R-27).
- **Consequences:** `docs/squads/semantics.md` and one test per rule. A change to any rule needs a new ADR.

## ADR-033 — One command guard, at the runtime kernel

- **Status:** proposed. Accepted after the M5-E3-T6 spike shows that every process a worker starts can go through the kernel's `ExecuteCommand`. On acceptance it supersedes the command-guard clause of ADR-010. If the spike fails, ADR-010 stands and this ADR is rejected with the reason.
- **Context:**
  - ADR-010 planned one Python guard in the worker, while the kernel keeps its linked `koda-security-core` check. That leaves the same rules in two languages, with a permanent parity suite to keep them aligned.
  - `shell_execute` already runs through the kernel, and `shell_bg` will (M1-E4-T10). Git and the other CLI tools run through `cli_runner` as local subprocesses.
- **Decision (proposed):**
  - Every worker-started process goes through the kernel's `ExecuteCommand`, with its cwd, environment allowlist (M1-E2-T4) and timeout.
  - The kernel's linked check is the only command guard, and the Python denylist copies are deleted.
  - The Rust tests own the rules. Python tests use a fake kernel client.
  - The guard is documented as a guard, not a sandbox.
- **Alternatives considered:**
  - A Python guard only. The kernel also starts processes itself, so it would still need a check.
  - Both guards with parity vectors (ADR-010 as written). This means a two-language suite to maintain indefinitely.
- **Consequences:** worker command execution depends on the kernel, as shell already does. The security sidecar fold (M5-E5-T1) no longer ports command rules to Python.

## ADR-034 — The MCP client stays on the shared aiohttp stack

- **Status:** accepted (2026-11-14, Principal Architect). Consistent with ADR-010 ("aiohttp is the single HTTP stack").
- **Context:**
  - The first draft planned to adopt the official MCP client SDK (M5-E3-T10).
  - The SDK adds a runtime dependency with transitive server-side packages and brings its own HTTP stack. That stack would bypass the pinned-resolver SSRF guard (M1-E3-T1) and the redirect rules (M1-E3-T3).
  - The actual gap is the missing Streamable HTTP and SSE transports (TD-040).
- **Decision:** keep the hand-rolled JSON-RPC client. Add Streamable HTTP and SSE on aiohttp, reusing the SSRF guard and the redirect rules, and prove them with real round trips against local reference servers.
- **Alternatives considered:**
  - The SDK with an HTTP transport wrapped by the guard. It would supersede ADR-010 and add a larger dependency.
  - The SDK as it ships. It bypasses the guard.
- **Consequences:** Koda maintains the protocol code. Revisit if the MCP specification moves faster than that upkeep, for example a protocol version Koda cannot speak.

## ADR-035 — Runtime-kernel RPC token: holders and threat scope

- **Status:** proposed. §13 applies (new production credentials; deployment change on existing installs). It is in approval batch 1 with M1-E6-T1.
- **Context:**
  - The kernel's gRPC is unauthenticated. `ExecuteCommand` and `EnsureAgentWorkers` are reachable from the backend network, which includes the web container (D-042, R-04).
  - ADR-001 rejects interim tokens for the other sidecars, because agent code in the kernel container could read them. The same argument applies to a kernel token unless its holders are stated.
- **Decision (proposed):**
  - The kernel listens on a UDS or loopback and requires a shared-secret metadata token. The token is generated at install or update and written to `.env` with mode 0600.
  - **Holders:** the supervisor (`app`) and the agent worker processes. Provider CLI and tool subprocesses never receive it, because the M1-E2-T4 allowlist strips it.
  - **Threat addressed:** network peers, chiefly the web container and the sidecars that are not yet folded. Code already running inside the kernel container is outside this control; ADR-002 (B) covers it.
  - The web container leaves the backend network.
  - **Upgrade:** `koda update` generates the token and recreates `app` and `runtime-kernel` together.
  - **Rollback:** the previous release ignores the token. Both directions are tested in CI.
- **Alternatives considered:**
  - mTLS: certificate management for a single link.
  - UDS file permissions only: this needs a volume shared by `app` and the kernel, and any process with that uid in either container could connect, so it adds no separation over a token.
- **Consequences:**
  - One more secret, which the backup includes (M2-E6-T1).
  - Residual risk: a same-uid process in the kernel container might read a worker's environment through `/proc`. M1-E2-T4 tests this, and R-01 records any residual.

## ADR-036 — Configuration drift is caught by a parity test

- **Status:** accepted (2026-11-14, Principal Architect). Supersedes these clauses of ADR-013: the key registry, the three-way classification, the reference doc generated from the registry, and the registry CI check. The rest of ADR-013 stands.
- **Context:**
  - ADR-013 planned a registry that classifies about 387 keys, a generated reference doc and a CI linter.
  - The actual problems are drift between `koda/config`, `.env.example` and `docs/config/reference.md`, and environment reads outside `koda/config`.
- **Decision:**
  - A test collects every key that `koda/config` reads (by AST) and diffs that set against `.env.example` and `docs/config/reference.md`, with a short committed list of documented exceptions.
  - A second check rejects `os.environ` and `os.getenv` reads outside `koda/config`.
  - There is no registry module and no doc generator (M5-E4-T2).
- **Alternatives considered:** the registry as ADR-013 wrote it, which is more machinery for the same detection.
- **Consequences:** the reference doc stays hand-written and readable, and it can no longer drift silently.

## ADR-037 — Deletion policy clarifications

- **Status:** accepted (2026-11-14, Principal Architect). Clarifies how the classes of ADR-018 apply. ADR-018 itself is unchanged.
- **Context:** the first draft:
  - bundled behaviour changes into deletion-only M4 tasks (M4-E1-T3, T6 and T10, and M4-E2-T2);
  - removed a documented overlay (Tempo) without approval;
  - left two inert controls unlabelled while their decisions were open (F-MEM-25, F-ADM-06).
- **Decision:**
  1. A documented configuration key that nothing reads has no runtime consumer, so its removal is class 1. It gets a changelog entry.
  2. A documented feature that never worked (a page, command, tool, overlay or integration) is class 2. Label it "Not available yet" first, and delete it only after approval.
  3. A deletion-only commit contains no behaviour change. Any behaviour a deletion would change is its own task, with a characterisation test and a changelog entry.
  4. When the full fix for a critical or high security defect waits on an approval, a reversible interim mitigation (label, disable or fail safe) ships first (MASTER_PLAN M1-E8), and the approval is escalated in the next batch.
- **Alternatives considered:**
  - Gate every documented removal, dead configuration keys included. This floods the operator with requests.
  - Allow behaviour changes inside removals. Removals would then no longer revert cleanly.
- **Consequences:** there are more and smaller tasks, and M4 commits revert cleanly.

## ADR-038 — Auth screens may show an account-independent rate-limit message

- **Status:** accepted (2026-11-14, Principal Architect, under the operator's delegated decision authority). Implemented by MASTER_PLAN M1-E1-T18.
- **Context:**
  - The "Auth screens" rule in `apps/web/CLAUDE.md` routes every authentication error, "rate-limited" included, through one generic message, so a user throttled by the per-client limit (D-004) sees "Invalid credentials." and keeps retrying, which extends the wait.
  - Two limits exist: a per-client bucket (`429` with `Retry-After`) that behaves identically for existing and unknown accounts, and a per-account lockout that only an existing account can trigger.
- **Decision:**
  - The per-client `429` gets its own localized message with the wait time. It reveals only that this client is throttled, never anything about an account.
  - Per-account lockout, wrong password, unknown user and invalid recovery code stay on the single generic key, and the backend keeps its timing floor.
  - The rule in `apps/web/CLAUDE.md` and `docs/security/authentication.md` is amended in the same change, with tests.
- **Alternatives considered:**
  - Keep the generic message for `429`: no enumeration benefit, worse recovery for real users.
  - Show a lockout message for the per-account limit as well: reveals that the account exists.
- **Consequences:** clearer feedback on throttling without weakening enumeration resistance.

## ADR-039 — One evaluator semantics: fnmatch for every rule (amends ADR-008 step 1)

- **Status:** accepted (2026-11-14, Principal Architect, under the operator's delegated decision authority). Implemented by ADR-002 AG-06, which absorbs MASTER_PLAN M1-E4-T9; delivery of rules to workers stays gated by AG-09 and AG-10.
- **Context:**
  - ADR-008 step 1 kept the runtime matcher for allow rules and added fnmatch only for deny rules, so that an allow rule with an interior wildcard could not start matching more calls.
  - ADR-002 AG-06 builds one engine that the control plane's validation and simulate route and the runtime both use, with fnmatch for every selector. The independent REV review of ADR-002 (VALIDATION_REPORT "M1-E2-T1 reviews") found that the two decisions contradict each other and that the ADR called AG-06 only "a precedence fix".
  - No dashboard-authored rule has ever been evaluated by the runtime matcher: `execution_policy` never reaches the worker (ADR-002 C6). The runtime reads only `AGENT_EXECUTION_POLICY_JSON`, which the control plane never sets. The semantics operators validated and simulated against are already fnmatch.
- **Decision:**
  - The one engine uses fnmatch for every rule, allow rules included. Precedence is: most restrictive decision first, then priority, then name. A rule's name is its audit `rule_id`.
  - ADR-008 step 1's safeguard moves to delivery. Before AG-10 delivers rules to workers, AG-09 replays every stored policy, and any `AGENT_EXECUTION_POLICY_JSON` value found on an install, under the legacy runtime matcher and under the engine. A non-empty allow-widening diff needs §13 sign-off with the report attached, as AG-10's gate already says.
  - M1-E4-T9 is folded into AG-06. Its done-when items are met by AG-06 (one engine, simulate equals runtime, the deny vectors) plus AG-09 (the replay).
  - ADR-008 steps 2 to 5 are unchanged.
- **Alternatives considered:**
  - Keep two matchers (ADR-008 step 1 as written): permanent dual semantics in one engine, for rules that have never run in a worker.
  - Limit AG-06 to precedence and keep M1-E4-T9 separate: two tasks change the same evaluator in opposite directions.
- **Consequences:**
  - An operator who set `AGENT_EXECUTION_POLICY_JSON` by hand with interior-wildcard allow rules sees those rules follow fnmatch after AG-06. `docs/operations/upgrade.md` says so, and AG-09 reports the affected rules.
  - Dashboard-authored rules keep the meaning they had in validation and simulation once delivered.
