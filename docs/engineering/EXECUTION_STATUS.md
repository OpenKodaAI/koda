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

## Active tasks

- DEFECT-BATCH-1 — round 1 done (workflow `wf_1ddc4a95-938`, 21 agents): all 7 defects verified real, each fix has tests that fail on the pre-fix code, every branch's full suite passed in its worktree. First review: approve for D-001/D-016, D-009, D-018, D-020 (minor items then fixed); request_changes for D-003, D-004, D-022 (then addressed). Round 2 running (`wf_4962a220-f9b`): fresh independent review of each final branch (two lenses for D-003/D-004/D-022), bounded address/re-review loops, and an integration review of `integrate/batch-1` (all 7 merged; one docs conflict in `docs/reference/api.md` resolved by keeping both sections). Full gates on the integration worktree (ea4e6e3) pass: Python 5081 passed / 205 skipped (61% line coverage), Postgres 191 passed / 2 skipped, web lint 0 errors, web 770 tests passed, web build ok. Follow-ups filed: D-220 (bundled nginx config, M1-E1-T16), D-221 (setup-code normalization, M1-E1-T17), D-004 remainder (rate-limit message, M1-E1-T18, ADR-038), D-222 (env-backed cancel, M3-E2-T6), D-223 (remaining outbound fetch paths, M1-E3-T8).
- WAVE-2 (two workflows, worktrees `/home/user/koda-wt/<task>` on `task/<task>` from `integrate/batch-1`): M1-E4-T1, M1-E4-T13, M1-E4-T10, AG-06, M0-E3-T2, M0-E1-T4 (`wf_54ec96f9-04b`) and M1-E8-T1, M1-E8-T3, M1-E1-T3, AG-02, AG-04, AG-05 (`wf_f6f3c9f3-4d8`). Each: implement with fail-before tests → two independent review lenses → bounded address/re-review (max 3 rounds). Merged by the orchestrator after full gates.
- M0-E4-T1 (dependency advisory triage, workflow): raw audits collected 2026-11-14 — pip-audit over the full uv lock (14 packages, 206 records / 157 GHSA), `pnpm audit` (5 critical, 41 high, 39 moderate, 8 low; production subset 5/17/12/2), RustSec advisory-db matched against both Cargo.lock files (29 findings in 17 crates). Per-ecosystem reachability triage with adversarial verification is writing `SUPPLY_CHAIN_TRIAGE.md`. `cargo-audit` could not be installed in this session (blocked by the session's permission policy), so a local matcher over the RustSec data stands in; Dependabot alerts cannot be exported from this session.
- AGENT-AUTONOMY: ADR done (`docs/engineering/adr/ADR-agent-native-tool-governance.md`, commit d72ac53; operator resolutions O-1..O-8 recorded). Implementation backlog AG-01..AG-32 starts after defect batch 1 merges (foundation wave AG-02..AG-09 first).


## Pending findings for the plan (verified by the orchestrator)

- **Supply chain** — GitHub Dependabot reports 352 open vulnerabilities on the default branch (23 critical, 163 high, 147 moderate, 19 low), shown on push 2026-11-14. Needs triage by ecosystem (uv.lock / pnpm-lock.yaml / Cargo.lock) and reachability before upgrades.

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
