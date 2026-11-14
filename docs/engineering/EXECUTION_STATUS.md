# Execution Status

Live state of the consolidation mission defined in [MISSION.md](MISSION.md).
This file reflects verified reality only. Update it at the end of every loop
iteration.

## Loop protocol (read first on every iteration / new session)

1. Re-read `MISSION.md` and this file.
2. Check `git log` on branch `claude/dreamy-cerf-mhvbwn` for work landed since the last entry.
3. Pick the highest-priority `ready` task from `MASTER_PLAN.md` (security/data integrity → broken journeys → architecture → core functionality → reliability → UX/a11y → perf → polish).
4. Understand → design → implement → validate (CLAUDE.md "Required Validation") → independent review → record evidence here and in `VALIDATION_REPORT.md`.
5. Commit with a message referencing the task ID and push to the branch.
6. Never mark a task `done` without recorded evidence (command + result).

## Environment facts

- Cloud environment `koda` (personal): limited network (package registries + Google Fonts); `AGENT_TOKEN` / `ALLOWED_USER_IDS` set to CI dummy values in fresh sessions.
- 4 CPUs / 15 GB RAM: workflow subagent concurrency is effectively 2.
- PostgreSQL 16 + pgvector can be installed locally (`apt-get install -y postgresql-16-pgvector`); Docker is not available, so testcontainers-based fixtures skip.
- Parallel worktrees: the pytest conftest builds the Rust security service per checkout (~1.5 GB `rust/target` each). Waves share one service built from the main checkout (start `rust/target/debug/koda-security-service` once with `SECURITY_GRPC_TARGET=127.0.0.1:50300`) and delete worktree `rust/target` dirs after merge. Once M0-E2-T1 is on the branch, worktrees opt in with `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:50300` (an ambient `SECURITY_GRPC_TARGET` is ignored; without the opt-in each session starts its own guard on a private Unix socket). A shared guard runs the Rust build it was started from, so runs that change `rust/koda-security-*` must not use it. Disk headroom was 7.9 GB with 7 worktrees.
- Disk budget (2026-11-14 08:30): with ~20 worktrees the disk reached 96 %. Main consumers were Rust build output (main checkout 5.1 GB; each worktree that runs `cargo` ~1.5 GB, `--release` more) and agents' full-repo baseline copies in the scratchpad (0.7-2.6 GB each). Rules for agent prompts: prove fail-before with `git stash`/`git worktree` on the same checkout rather than copying the repo; build Rust only when the task touches Rust; delete worktree `rust/target` after merge. The main checkout keeps only `rust/target/debug/koda-security-service` (the shared guard binary); main-checkout test runs use `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:50300`. The shared guard runs as a harness background task with a 2 h limit and is restarted on the loop heartbeat. `tests/integration/conftest.py::cargo_build_release` builds `koda-bot-gateway` in release (~530 MB) once per checkout when the binary is missing, so non-Rust worktrees get a hard link to one prebuilt binary at `rust/target/release/koda-bot-gateway` (`../koda-wt/.shared-bin`).
- Outbound web access is restricted: reference-product research relies on search results; anything not verifiable is marked as such.

## Current phase

**Phase Five — execution loop** (Phase Zero and Phase One complete).

| Step | Status | Evidence |
|---|---|---|
| Mission stored durably | done | `MISSION.md` |
| Validation baseline | done | `QUALITY_BASELINE.md` |
| Phase Zero discovery | done | `SYSTEM_INVENTORY.md`, `ARCHITECTURE_AUDIT.md`, `FEATURE_MATRIX.md` (430 features), `TECHNICAL_DEBT.md`, `REFERENCE_RESEARCH.md` (commit 3665c37) |
| Target architecture, ADRs, risks, backlog | done | `MASTER_PLAN.md` (M0–M10, reviewed and revised; §5.3 operator resolutions), `DECISIONS.md`, `REMAINING_RISKS.md`, `adr/ADR-agent-native-tool-governance.md` (commits d72ac53, 5628c04) |
| Execution | running | defect batch 1, then the plan's first tasks and the AG foundation wave |

## Completed tasks

- P0-BASELINE — all required gates executed; results in `QUALITY_BASELINE.md`.
- P0-FIX-CARGOFMT — documented `cargo fmt --check --manifest-path rust/Cargo.toml` fails on rustfmt 1.9 ("Failed to find targets"); corrected to `cargo fmt --all --check ...` in CLAUDE.md, README.md, packages/cli/README.md. Evidence: new command rc=0; `tests/test_installation_assets.py` + `tests/test_top_tier_roadmap_assurance.py` 41 passed.

- M0-PG-FIXTURES — Postgres-marked suite (186 tests) now runs and passes; DSN scoped per test with no session leaks; new `python-postgres-tests` CI job. Reviewed (approved; major + minor items fixed). Evidence: `VALIDATION_REPORT.md`.

- SEC-PLACEHOLDER-SECRETS — unedited `.env.example` placeholders (`replace-with-*`) authenticated as break-glass owner / runtime UI token on the documented manual install (port 8090 published on all interfaces). Fixed: placeholders treated as unset in Python, web and the runtime-token broker; web checks the secret before contacting the control plane (no lost recovery codes); `scripts/generate_env_secrets.py` (0600, mkstemp, auth-only on existing installs) used by docs and CI smoke; doctor checks hardened. Two security review rounds (round 1: 2 major + 6 minor; round 2: approve, 4 minor → fixed). Evidence: `VALIDATION_REPORT.md`.

- DATA-UNINSTALL-VOLUMES — `koda uninstall` no longer deletes data volumes without `--purge`; `--purge` refuses non-Koda directories and removes volumes before the `.env`. Reviewed (approve). Evidence: `VALIDATION_REPORT.md`.

- M0-E2-T1 — test sessions own their security guard (private Unix socket; explicit `KODA_TEST_SECURITY_GUARD_TARGET` opt-in to share); two concurrent full runs pass with a decoy guard on 50065. Reviewed (approve; 11 minor items fixed). Evidence: `VALIDATION_REPORT.md`.

- M0-E4-T1 — dependency advisory triage: `SUPPLY_CHAIN_TRIAGE.md` (50 packages, 278 advisories; every critical/high non-upgrade disposition challenged by a skeptic, every upgrade target checked against the registry; 3 claims overturned and corrected). Remediation planned as M1-E7-T2..T4 (ordered batches) plus M1-E7-T10..T12 (code-level hardening); new defect D-224 (dev dependencies in production images). Evidence: `VALIDATION_REPORT.md`.

- DEFECT-BATCH-1 — seven verified high/critical defects fixed and merged (a4a441e): D-001/D-016 scheduled jobs, D-003 SSRF guard, D-004 login rate limiting, D-009 `/cancel`, D-018 password recovery, D-020 circuit breakers, D-022 event-stream resume. Two independent review rounds plus an integration review; full gates on the merged tree. Plan tasks M1-E3-T1, M1-E1-T2, M3-E1-T1, M3-E1-T2, M3-E2-T1, M3-E7-T1, M3-E8-T1, M3-E8-T2 done; FEATURE_MATRIX: 8 features left `broken`. Evidence: `VALIDATION_REPORT.md`.

## Active tasks

- WAVE-2 (two workflows, worktrees `../koda-wt/<task>` (sibling of the checkout) on `task/<task>` from `integrate/batch-1`): M1-E4-T1, M1-E4-T13, M1-E4-T10, AG-06, M0-E3-T2, M0-E1-T4 (`wf_54ec96f9-04b`) and M1-E8-T1, M1-E8-T3, M1-E1-T3, AG-02, AG-04, AG-05 (`wf_f6f3c9f3-4d8`). Each: implement with fail-before tests → two independent review lenses → bounded address/re-review (max 3 rounds). Merged by the orchestrator after full gates.
- AGENT-AUTONOMY: ADR done (`docs/engineering/adr/ADR-agent-native-tool-governance.md`, commit d72ac53; operator resolutions O-1..O-8 recorded). Implementation backlog AG-01..AG-32 starts after defect batch 1 merges (foundation wave AG-02..AG-09 first).


## Pending findings for the plan (verified by the orchestrator)

- **Supply chain** — triaged (M0-E4-T1, `SUPPLY_CHAIN_TRIAGE.md`); remediation is M1-E7-T2..T4 and T10..T12. Dependabot's 352 alerts could not be exported from this session, so they are compared by count, not reconciled one-to-one.

- **APPROVED 2026-11-14 (Option C, long-term) — CRITICAL (agent autonomy vs. governance)** — design workflow running (understand → 3 designs → judge panel → ADR `docs/engineering/adr/ADR-agent-native-tool-governance.md`); implementation follows the ADR backlog. — provider CLIs run with every native tool enabled and approvals off: Claude `--permission-mode bypassPermissions` with no tool allow/deny list (`koda/services/claude_runner.py:339`, mode chosen in `queue_manager.py:3101` even for `supervised` agents), Codex defaults `CODEX_SANDBOX=danger-full-access` + `approval_policy=never` (`koda/config.py:226-227`, `codex_runner.py:278`), Gemini `--approval-mode yolo`. Native shell/file/web tools therefore bypass Koda's command guard, approval broker and sandbox policy. Workers run as `botuser` in `runtime-kernel`, whose isolation is cgroup limits only (`rust/koda-runtime-kernel/src/isolation.rs`), with the shared `koda-state` volume mounted — the same volume that holds `control_plane/.master.key`, which decrypts every stored secret. A prompt injection reaching an agent could plausibly read the key and secrets (code-verified; not yet proven at runtime — no Docker here). Options: (A) governed by default — restrict provider-native tools to a safe allowlist (or plan/read-only) unless an agent's policy explicitly opts into native autonomy, keeping governed actions in Koda's dispatcher; (B) confine — run provider CLIs without the state volume/secrets (separate mount set, no master key, network limits); (C) both: A now, B next. Recommended: C. Impact of A: agents relying on native shell/edit lose them until opted in.

- **DONE 2026-11-14 — NET-LOOPBACK (operator-approved, reviewed twice) (network exposure)** — API always on `127.0.0.1`; dashboard `${WEB_PUBLISH_ADDRESS:-127.0.0.1}`; prod overlay no longer repeats ports; contract test `tests/test_compose_port_exposure.py`. Original finding: — `docs/install/vps.md` promises the dashboard (3000) and control-plane API (8090) are bound to localhost behind a reverse proxy, and `docs/security/authentication.md` says the backend is bound to `127.0.0.1:8090`. Reality: (a) the packaged installer's `packages/cli/release/bundle/docker-compose.release.yml` publishes both on all interfaces; (b) base `docker-compose.yml` does too; (c) `docker-compose.prod.yml` *adds* loopback bindings but Compose merges `ports` lists rather than replacing them (skeptic-confirmed), so it does not remove the public ones. Proposed: bind both to `127.0.0.1` by default (`!override` in the prod overlay, loopback in the release bundle and base compose) with an explicit opt-in variable for direct LAN access. Impact: anyone currently opening `http://<server>:3000` directly would need the reverse proxy or the opt-in. Operator approved the loopback default with explicit opt-in.
- `scripts/doctor.py` checks `KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY` but `.env.example` defines `S3_SECRET_ACCESS_KEY` → false "object_storage_secret_key: false" on manual installs.
- `POSTGRES_PASSWORD` / `S3_*` placeholders are still accepted (compose `:?` rejects only empty); reachable from the `backend` network, which includes `runtime-kernel` where agent tool code runs.
- `RuntimeAccessService` (`koda/services/runtime_access_service.py:50`) accepts an empty HMAC key; only call sites guard it.
- CLI recovery (`packages/cli/bin/koda.mjs:629`) sends the raw comma-separated `CONTROL_PLANE_API_TOKEN` as bearer → breaks during `new,old` rotation.
- Internal gRPC sidecars are unauthenticated on the `backend` network.
- Packaged install dir `~/.koda` and a source checkout named `koda` share the compose project name `koda` (same volume names); needs a pinned, distinct project name plus an install migration.
- `CHANGELOG.md` is the changelog of an unrelated project (`@googleworkspace/cli`); needs replacing with Koda's own.
- Web build had one transient Turbopack `next/font/google` resolution failure (passed on retry); watch for recurrence.

## Blocked tasks

_None._ (GitHub push access restored 2026-11-14; branch `claude/dreamy-cerf-mhvbwn` pushed.)

## Discovered regressions

_None._ Note: test runs sharing the machine with audit agents must use their own database. A shared run produced 111 spurious failures when another session's security-guard service on port 50065 went away; M0-E2-T1 removes that failure mode.
