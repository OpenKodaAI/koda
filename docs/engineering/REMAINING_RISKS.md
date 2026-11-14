# Remaining Risks

The risk register for the consolidation mission ([MISSION.md](MISSION.md) §5 Phase One deliverables, §14).
It was built from the Phase Zero audit at `7b848cf` plus the in-review working tree, and revised on
2026-11-14 together with revision 1 of the plan. Each mitigation points at tasks in
[MASTER_PLAN.md](MASTER_PLAN.md) and decisions in [DECISIONS.md](DECISIONS.md).

This register reflects what is verified, not what is hoped for. A risk is `closed` only with evidence in
[VALIDATION_REPORT.md](VALIDATION_REPORT.md) for every mitigation it names. Update it at the end of each
loop iteration and at every milestone (M10-E1-T4).

## Scales

| Field | Values |
|---|---|
| Likelihood | **L** unlikely in normal use · **M** plausible · **H** expected, or already observed |
| Impact | **L** minor or cosmetic · **M** a feature broken or degraded · **H** a security breach, data loss or a core journey broken for everyone · **Critical** compromise of every secret, or unrecoverable loss of all data |
| Status | **open** no mitigation in progress · **mitigating** mitigation approved or in progress · **accepted** risk-accepted by the operator, with the date · **closed** mitigated, with evidence |
| Owner | Role codes from MASTER_PLAN §2 |

Evidence strength follows the source labels: verified, code-read, or unverified. Where a risk rests on
code reading only, the risk text says so. "Batch n" refers to the approval batches in MASTER_PLAN §5.3.

## Open and mitigating risks

### Security

| ID | Risk | L | I | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R-01 | Provider CLIs run their native tools with permissions bypassed, so Koda's gates cover only `<agent_cmd>`. Workers mount the volume holding `.master.key` and receive the DSN and the S3 secret. A prompt-injected agent could read the key and decrypt every secret. Code-verified, not runtime-proven. | M | Critical | ADR-002 (Option C, approved 2026-11-14): M1-E2-T1 (in progress), M1-E2-T2, M1-E2-T4 (environment and cwd allowlist); M1-E2-T3 and M1-E2-T5 need sign-off (batch 2) and a restore drill. Residuals: network limits for provider CLIs are deferred until the kernel has a mechanism, and a same-user process may read a worker's `/proc` environment (M1-E2-T4 tests it). | SEC | mitigating |
| R-02 | The control-plane API (8090) and the dashboard (3000) were published on all interfaces in the base, release and prod compose files, contrary to the docs. | L | H | NET-LOOPBACK = M1-E1-T1 (`307349e`, `52ffc26`), ADR-003: contract test, full pytest and reviewer renders pass. It stays `in-review` until a GitHub Actions docker-smoke run is recorded. The cluster overlay's fixed host port with `replicas: 3` follows Q-1 (M5-E6-T9 or M5-E6-T13). | OPS | mitigating |
| R-03 | Dependency advisories: triaged 2026-11-14 in SUPPLY_CHAIN_TRIAGE.md (50 packages, 278 advisories). Reachable critical/high remain until remediation: Python certifi (critical, on-path attacker with a distrusted intermediate), pillow, pypdf, aiohttp, urllib3 (high); Node ws (high, pre-auth DoS), zod; next (critical, disputed, treated as reachable); Rust rustls-webpki/webpki-roots (bot-gateway TLS), postgres-protocol (cluster mode without TLS). Production images also ship the dev dependency group (D-224). | M | H | M1-E7-T2..T4 (batches P1–P5, N1–N4, R1–R6), M1-E7-T10..T12 | SEC | mitigating |
| R-04 | Internal gRPC is unauthenticated plaintext. The kernel's `ExecuteCommand` and `EnsureAgentWorkers`, and bot-gateway `RegisterBot`, are reachable from the backend network, which includes the web container. | M | H | M1-E6-T1 (kernel UDS plus token, web off the backend network; needs approval in batch 1; token holders and threat scope in ADR-035); ADR-001 folds the other sidecars (M5-E5) | SEC | open |
| R-05 | SSRF: fixed for the shared HTTP client (D-003, merged a4a441e: `0.0.0.0`, IPv4-mapped IPv6, `100.64.0.0/10`, rebinding, IDNA host mismatch). Remaining: the MCP client classifier and redirects, OAuth discovery, browser rebinding, artifact yt-dlp, image downloads and operator base-URL fetches (D-223, D-027, D-029, D-131). | M | H | M1-E3-T2 to T8; ADR-010, ADR-034 | SEC | mitigating |
| R-06 | Skill and plugin package code runs in process behind a bypassable denylist. The model can approve its own security review, and approved files can change after the scan (TOCTOU). | M | H | M1-E4-T3, M1-E4-T11, M1-E4-T12 (ready); interim M1-E8-T2 forces code-bearing packages through operator review; M1-E4-T4 needs approval (batch 1) | SEC | open |
| R-33 | Tool output, web pages and MCP tool descriptions reach the model without escaping or untrusted-data framing, which enables prompt injection that steers tool use. | M | H | M1-E4-T2; adversarial suite extended | SEC | open |
| R-34 | Personal API tokens survive a password reset or change. After recovering from a compromise, old `kpat_` tokens keep owner access, including plaintext secret reads. | L | H | M1-E1-T9 (needs approval, batch 1); M6-E2-T2 (scopes, needs approval) | SEC | open |
| R-35 | The login rate limiter trusts any `X-Forwarded-For`, and the BFF forwards no client IP. The result is a trivial bypass on 8090 and an anonymous lockout of the owner through the web (observed, J-15). | H | M | M1-E1-T2 (in progress, DEFECT-BATCH-1; started early, so a real-path regression test is required before done) | SEC | mitigating |
| R-36 | Unauthenticated `onboarding/status` returns agent ids, owner contact details, the Telegram allowlist, provider state and server paths (observed). | H | M | M1-E1-T3 | SEC | open |
| R-37 | The control plane never calls `setup_logging()`, so there is no redaction. The bootstrap setup code is logged in plaintext, and rich tracebacks dump local variables (observed). | H | M | M1-E1-T4 | SEC | open |
| R-38 | Artifact auto-discovery walks the work dir, which defaults to home, and attaches any recently modified file, including files from other tasks or users. Code-read. | M | M | M1-E4-T8 (Q-20 default) | SEC | open |
| R-42 | Squad administration tools (elect, demote, Telegram bind and unbind) have no caller authorization, an elected coordinator bypasses the participant and private-thread checks, failed break-glass audit writes are suppressed, and `agent_broadcast` crosses workspaces. Reachable only with squads enabled. | L | H | M1-E5-T1, M1-E5-T2, M1-E5-T4 | SEC | open |
| R-43 | Channel-gateway pairing codes (about 36 bits) have no attempt limit, and identity state is a whole-file JSON rewrite shared by two processes. Code-read. | L | M | M1-E5-T3 | SEC | open |
| R-54 | Background shell (`shell_bg`) bypasses both the runtime kernel (its cgroups) and the approval check, so it runs outside the guard while `shell_execute` fails closed. TECHNICAL_DEBT files it as D-162, low reliability; the plan reclassifies it as high security. Code-read. | M | H | M1-E4-T10 (ready), a hard dependency of M1-E2-T4 and M3-E3-T1; adversarial test that `shell_bg` obeys the same policy and kernel path as `shell_execute` | SEC | open |
| R-55 | Fixing D-011 makes policy-approved shell, git and supervised writes run for the first time, which widens what agents actually do. Shipped before the git option-injection fix (D-026), the background-shell fix and path parity, it would put those holes live. | M | H | M3-E3-T1 is `needs-approval` (batch 1) with a report of the agents and rules affected, and depends on M1-E2-T1, M1-E4-T1, M1-E4-T10 and M1-E4-T13; its done-when requires the D-026 probes and the guardrail suite to pass on the live paths | SEC | open |
| R-57 | Authorization outside the control plane has no matrix test: the worker runtime HTTP and WebSocket API (about 57 routes, on by default, authorized per route through `X-Runtime-Token`) and the Next.js BFF routes. A route without a check would go unnoticed. | M | H | M0-E3-T9 (runtime API matrix), M0-E3-T10 (BFF route inventory) | SEC | open |

### Data integrity and privacy

| ID | Risk | L | I | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R-07 | The master key is a single point of failure. It has no backup tooling, is reused as the HMAC key, has no working rotation path, and sits on a volume that workers share. Losing it makes every secret unrecoverable. | M | Critical | M2-E6-T1 (backup including the key, with a restore drill in CI; moved into M2); M1-E6-T3 (HKDF signing key); M1-E2-T3 and M5-E6-T11 need approval (batch 2) and cite a restore drill; ADR-025, ADR-026, ADR-029 | OPS | open |
| R-10 | Migrations are forward-only and non-transactional, and race across processes. `koda update` rollback restores code only. The planned casing and typing migrations rewrite existing rows. | M | H | M2-E6-T2 (backup before update), then M2-E2-T2 (atomic, locked runner with a lock budget); M2-E3-T5 and M5-E1-T5 need approval and a restore drill; ADR-004, ADR-028, ADR-029 | BE | open |
| R-17 | `replace_approval_grants` deletes every agent's grants on each partial use, and approval tables overflow on Telegram ids above 2^31, so entries are lost on restart. | H (2 or more agents) | H | M2-E1-T1 (with a stated rule for legacy grants that have no agent), M2-E1-T2; ADR-009 | BE | open |
| R-18 | Retention never runs: the purge targets missing tables, and the runtime tables are never purged. Query, audit and runtime tables grow without bound, and sweeps slow down. | M | M | M2-E5-T1 (report-only, ready); M2-E5-T2 (needs approval, batch 2; first purge needs a fresh backup); M9-E1-T4 | BE | open |
| R-26 | Costs are under- and over-counted: failed and fallback attempts are free, child totals go stale, and Codex double-counts. `budget_exceeded` is never read, so budgets do not stop spend. | H | M | M2-E4-T2 (cost accounting); M2-E4-T5 (budget enforcement or removal, decision Q-23) | BE | open |
| R-39 | `/forget` only deactivates memories. Content and redacted previews remain, contrary to what users expect "forget" to do. | H | M | M2-E5-T3 (needs approval, batch 2, after a restore drill); M6-E4-T2 (edit and deactivate from the UI); ADR-024 | AIM | open |
| R-44 | Agent hard delete orphans secrets and about 12 per-agent tables, and a recreated agent with the same id inherits the old secrets. Create and clone silently reuse an existing agent on id collision. | M | M | M2-E3-T1, M2-E3-T2 (ready); M2-E3-T3 (needs approval, batch 2, after a restore drill); ADR-023 | BE | open |
| R-45 | Multi-statement writes (owner registration, password reset, deletes) are not transactional, so a mid-way failure can leave, for example, an owner without recovery codes. | L | H | M2-E2-T1 | BE | open |
| R-46 | Task retries replay side-effecting tools (writes, shell, HTTP) after a later provider error. | M | H | M2-E4-T1; characterised by M0-E3-T11; ADR-006 | BE | open |
| R-56 | Upgrade migrations could hold write-blocking locks on hot tables. The planned index builds and backfills (casing, `napkin_log` full text, base importance, typed columns, BIGINT) would stall running agents if each ran in one transaction. | M | M | ADR-028: an online migration kind and a lock budget in M2-E2-T2, tested on a 1-million-row table; the migrations gate rejects transactional index builds on large tables (M2-E2-T5) | BE | open |
| R-58 | Folding the artifact and memory engines into Python could leave data written by the Rust engines unreadable, or make a downgrade impossible. | L | H | Compatibility fixtures seeded by the current engines, plus previous-release rollback tests (M5-E5-T2, M5-E5-T10); identical projection snapshots on a seeded copy (M5-E5-T4) | BE | open |

### Broken journeys and reliability

| ID | Risk | L | I | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R-16 | Scheduled jobs never fire (D-001, the only critical defect), and routines created on the web never activate. Users relying on reminders or recurring jobs get nothing, silently. | H | H | M3-E1-T1, M3-E1-T2 (in progress, DEFECT-BATCH-1; started early); M0-E3-T4 characterisation | BE | mitigating |
| R-19 | Synchronous database and gRPC calls block event loops for up to 30 s, and the per-user lock is held across slow awaits while PTB processes updates one at a time. The result can be bot-wide stalls, with `/cancel` blocked. Code-read. | M | H | M3-E2-T3, M5-E1-T3 (p99 loop lag under 100 ms with a 2 s database delay), M5-E1-T4, M9-E1-T1; ADR-012 | BE | open |
| R-20 | Circuit breakers latch open permanently after a transient failure, so the scheduler, runners, web search and TTS stay down until a restart. Verified. | M | H | M3-E8-T2 (in progress, DEFECT-BATCH-1); ADR-006 | BE | mitigating |
| R-47 | `/cancel` does not stop running light tasks, and cancelling kills the user's queue worker. Verified. | H | M | M3-E2-T1 (D-009 part in progress, DEFECT-BATCH-1, started early; D-087 and D-088 open); M3-E2-T4 (cascade to child runs and squad tasks) | BE | mitigating |
| R-48 | Policy-approved `shell_execute`, `git_*` and supervised writes always fail in production, and dashboard approvals cannot see worker approvals. This was hidden by a global test fixture. | H | H | M0-E2-T4; M3-E3-T1 (needs approval, batch 1; see R-55); M3-E3-T2; designed under AGENT-AUTONOMY-ADR (M1-E2-T1); ADR-009 | SEC | mitigating |
| R-49 | Memory recall is filtered to the in-flight task, so cross-session memory does not work, and the relevance threshold admits zero-overlap memories. Utility feedback is a no-op as a result. | H | M | M0-E3-T5, M3-E4-T1, M3-E4-T2, M3-E4-T7 | AIM | open |
| R-27 | Agent loops in squads (`agent_send` ping-pong, delegation cycles whose limits reset every hop, advisory budget pause) can burn tokens without bound. Squads are off by default, which lowers the likelihood. | L (off by default); M if enabled | H | M3-E6-T4, M3-E6-T5; ADR-016; semantics in ADR-032 (M3-E6-T7); default-on gated by Q-9 | AIM | open |
| R-50 | Squad post-processing deadlocks on the per-user lock, and no-task coordinator modes leave the user without a reply. Reachable only with squads enabled. | L (off by default) | H | M3-E6-T1, M3-E6-T2 | AIM | open |
| R-28 | The backup and restore runbook cannot be run as written (dead knobs, a missing endpoint, an unverified `weed s3 sync`), so recovery has never been tested. | M | Critical | M2-E6-T1 (moved into M2; a CI restore drill is a dependency of every destructive or irreversible task, ADR-029) | OPS | open |
| R-29 | A packaged install (`~/.koda`) and a source checkout named `koda` share the compose project name and therefore the volumes. Data can mix, or be deleted by the other install's `down -v`. | L | H | M7-E2-T3 (needs approval, batch 2, after a restore drill) | OPS | open |
| R-51 | Health reports `degraded` with HTTP 200, so orchestration never sees failures. Runtime-kernel state does not survive a restart and SIGTERM is not handled. The reconcile loop floods logs (2.2 MB in 9 minutes, observed). | M | M | M7-E1-T1, M7-E1-T2, M7-E1-T3 (graceful shutdown); M7-E1-T5 and T6 (restore and reconcile) wait on Q-8; M7-E5-T1 (log rotation) | OPS | open |
| R-52 | Control-plane outages show as $0 or empty data instead of an error, so operators act on false information. | M | M | M3-E8-T3; ADR-020 | FE | open |
| R-59 | There is no emergency stop. Nothing stops every agent, running task, child run and squad thread at once, and `/cancel` does not cascade to child runs or delegated squad tasks (mission §7.5). | M | H | M3-E2-T4 (cascade), M3-E2-T5 (stop all agents, reusing pause and cancel); journey in M3-E9-T1 | BE | open |
| R-60 | Resource use and growth are unbounded: no container has memory or CPU limits, Docker logs are not rotated, and the new backups (M2-E6-T1) add disk use. A busy install could fill its disk. | M | M | M7-E5-T1 (limits from measurements, log rotation, backup retention) | OPS | open |

### Supply chain and licensing

| ID | Risk | L | I | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R-15 | Two minified bundles from another vendor's desktop app (1.6 MB) are committed at the root and in history, and are likely not redistributable under Apache-2.0. The root `CHANGELOG.md` belongs to an unrelated project. | M | M | M1-E7-T6 (remove from HEAD); M1-E7-T7 (history purge, needs approval and licensing review, Q-17) | OPS | open |
| R-21 | Provider CLIs are installed unpinned, base images and several actions float on tags, and two workflows install without the lock. An upstream compromise or breaking release ships without review. | L | H | M1-E7-T1, M1-E7-T5; ADR-021 | OPS | open |
| R-31 | The bot-gateway and policy-engine images are never built or scanned in CI, and may hit a glibc mismatch at runtime. Unverified. | M | L | M7-E4-T1 (scan every image), M5-E5-T8; or removal (M5-E5-T6, T7, Q-22) | OPS | open |
| R-30 | The web build needs network access to Google Fonts. One transient Turbopack `next/font` failure has been observed. | L | L | M8-E5-T5 (fewer fonts); vendor the font files if it recurs | FE | open |

### Engineering and delivery

| ID | Risk | L | I | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R-08 | Refactoring the god modules could change behaviour that no test covers. No test executes `_execute_single_task`, 212 of 324 test files mock, and the Rust sidecars other than security and bot-gateway are tested only against fakes. | H | H | M0-E3-T2..T6 and M0-E3-T11 first; ADR-005 strangler rule (move, then change); ADR-027; REV review on high-risk tasks; pure structural splits moved to M9 | QA | open |
| R-09 | Consolidating policy could silently change effective permissions, since the two evaluators disagree and 8 policy stores overlap. | M | H | M1-E4-T9 (fail-safe only, with a replay that refuses any allow widening); M5-E3-T2 (offline replay report); approval for M5-E3-T3 and each per-store task (batch 4); ADR-008 | SEC | open |
| R-11 | External API clients may depend on contracts that will change: legacy route families, the error body shape, the 401 on failed login, the 409 on id collision, the 503 on outage, the `/health` payload. Consumers are unknown for a self-hosted single-owner product. | L | M | ADR-030: a one-release compatibility window for body changes and route removals (M5-E6-T1, M5-E6-T8, M5-E6-T12); every contract-changing task writes its changelog entry, checked by M10-E1-T3 | BE | open |
| R-12 | This environment cannot produce end-to-end evidence. There is no Docker daemon, no provider credentials and only limited egress, and no agent turn has run end to end. Without discipline, mocked results could be reported as proof. | H | H | M0-E1-T5 (CI credentials; operator action and paid-service approval, batch 1); M3-E9-T2 (real-provider checkpoint after M3); M10-E1-T5 (final acceptance after M1 to M9); MASTER_PLAN §9; ADR-027 | QA | open |
| R-13 | The new `python-postgres-tests` CI job has never run, is not a required check, and would pass with every test skipped. | M | M | M0-E1-T2; M0-E1-T3 (operator action) | QA | open |
| R-14 | Test runs on a shared host attach to another session's security-guard service. One such run produced 111 spurious failures. | M | M | M0-E2-T1; isolated database and port per run until then | QA | open |
| R-22 | 24 product decisions (Q-1 to Q-24, 15 still open) gate 9 tasks, 39 tasks need an operator approval, and their dependents wait behind them. Security fixes that wait on approval are protected only by interim mitigations meanwhile, and effort could go into features that are later removed. | H | M | MASTER_PLAN §5.3 approval batches (batch 1 now); interim mitigations M1-E8 (ADR-037); ADR-018 (label, then remove); decision tasks that open one task per outcome | ARCH | open |
| R-23 | Documentation contradicts the code: the auth contract (ports, rate budgets, TTL, redaction), the threat model, the web design guide, the install paths and the squad flags. CLAUDE.md requires auth doc parity in the same change. | H | M | M1-E1-T8 (parity test); M1-E9-T1 (threat model and matrices); M8-E5-T3; M6-E1-T6; M10-E1-T1, M10-E1-T2 | PROD | open |
| R-32 | Execution capacity is 4 CPUs, which means about 2 concurrent subagents, and Rust builds are expensive. The 342-task plan may slip, and parallel edits may conflict. | H | L | Deletion first (M4); lanes and serialization (MASTER_PLAN §8); incremental build targets; the plan lint keeps statuses honest (M0-E1-T4) | ARCH | open |
| R-40 | Tests give false assurance. String-grep infrastructure tests missed the prod, cluster and observability breakage. The coverage gate is 53.5% against 61% measured, and docker-smoke only proves that the login page renders. A task was marked done without its CI evidence. | M | M | M0-E3-T7, M0-E3-T8, M5-E5-T9, M9-E3-T5; the evidence rule and plan lint (M0-E1-T4); ADR-027 | QA | open |
| R-41 | Large removals (about 12k web lines, sidecars, dead Python clusters) could delete something that has an unseen consumer, for example an external caller of a BFF route. | L | M | ADR-018 and ADR-037 (proof of no consumer; deletion-only commits that revert cleanly); the BFF route inventory (M0-E3-T10); REV review | REV | open |

### Product scope and experience

| ID | Risk | L | I | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| R-24 | Every agent must be a Telegram bot: publish fails without `AGENT_TOKEN` and the worker will not start. Dashboard-only use (J-11) is impossible, although the docs present Telegram as optional. | H | M | M3-E5-T3 (moved into M3 as a broken journey; Q-2 in batch 1); J-11 in the M3 exit criteria; README correction | PROD | open |
| R-25 | Knowledge retrieval runs over empty tables in the only working mode, so operator knowledge is never used. The grounding gate may force `needs_review` as a result (that part is unverified). | M | M | M6-E1-T5 (ready); M6-E1-T10 (label the assets UI); M6-E1-T4 (Q-6 decision, opening one task per outcome); ADR-015 | AIM | open |
| R-53 | The UI offers functionality that does not exist: 8 channels that show "connected", generative UI blocks, composer mentions that are dropped, routine connectors and read-only and path controls, knowledge assets that are saved but never used, video and music default slots that only raise, and an improvement-proposal "apply" that only writes a ledger row. Operators are misled (MISSION §6.3). | H | M | Labels first: M1-E8-T1, M3-E1-T8, M3-E5-T2, M6-E1-T2, M6-E1-T9, M6-E1-T10, M6-E3-T5 (ready); removals: M4-E3-T4 and M6-E3-T3 (need approval) | PROD | open |
| R-61 | "Learning" has no definition or measure, and the memory correction journey has never been validated. Users cannot tell what an agent learned, from where, or how to undo it (MISSION §7.4). | H | M | ADR-031 (proposed definition); M3-E4-T7, M6-E4-T1 (measures), M6-E4-T2 (edit and deactivate journey) | AIM | open |
| R-62 | Interaction states are inconsistent across routes: no permission-denied (403) or offline state, mixed loading and empty treatments, and several form and dialog variants (MISSION §6.2, §6.3). | H | L | M8-E6-T1 to T3 (state matrix, 403 and offline states); M8-E5-T8 to T13 (design-system categories); M8-E2-T5 (IA review) | UX | open |

## Closed or reduced risks

| ID | Risk | Closed by | Evidence | Residual |
|---|---|---|---|---|
| RC-01 | Unedited `.env.example` placeholders authenticated as the break-glass owner on a published port | SEC-PLACEHOLDER-SECRETS (`3f895ee`) | VALIDATION_REPORT.md, two security review rounds | Postgres and S3 placeholders are still accepted: warned by M1-E8-T3, refused by M1-E1-T10 (needs approval, batch 1) |
| RC-02 | `koda uninstall` without `--purge` deleted every data volume, master key included | DATA-UNINSTALL-VOLUMES (`7b848cf`) | VALIDATION_REPORT.md | Project-name collision (R-29) |
| RC-03 | The Postgres persistence path was untested everywhere | M0-PG-FIXTURES (`30a7fe5`) | 186 passed, 2 skipped locally | The CI job has not run (R-13) |
| RC-04 | The documented `cargo fmt` gate command always failed | P0-FIX-CARGOFMT | VALIDATION_REPORT.md | — |

R-02 moved back from this table to `mitigating` in revision 1: its task's done-when includes a docker-smoke
CI run that has not been recorded (mission §11).

## Review cadence

- **Every loop iteration:** update the status of any risk the completed task touched, and cite the evidence.
- **Every approval batch:** record each answer, and move the affected risks to `mitigating`, `accepted` (with the operator's date) or leave them `open`.
- **Every milestone:** re-score likelihood and impact, and add the new risks the milestone revealed (M10-E1-T4).
- **Before the production-readiness call (MISSION §11):** every critical or high risk is `closed` or `accepted` by the operator, with a date. R-12 must be closed by real end-to-end evidence (M10-E1-T5).
