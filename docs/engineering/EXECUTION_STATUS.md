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
7. **Update the progress tracker at the end of every iteration** (the operator follows it): https://claude.ai/artifact/28r7JGEPHunFQ9VwFygpph (a dashboard). Its data are the JSON files in `docs/engineering/tracker/` (milestones, phases, waves, blockers, log; `index.html` is the page). Edit the files to match the records, upload each changed file to the artifact as an asset, point its `datasets/<id>` document at the new `/_blob/<id>` with fresh `updated` and `edit` stamps, delete the replaced asset, append a `log` row for each event, and commit the files with the records.

## Workflow rules (no rework, no over-engineering) — 2026-11-14, revised 2026-11-15

Learned from waves 2A–7 and the ADR-002 rounds. Every workflow script follows them. Rule 10 replaces rules 1–3 for task lanes; rules 1–3 still apply to design documents (ADRs).

**Why rule 10 (measured 2026-11-15 01:05 from the workflow journals):** across waves 5–7, agents spent 906 minutes implementing and 859 reviewing. Wave 5 started 18:59 and was still in round 3 at 01:05. Each task went through 2–3 implement-review rounds plus a leftovers round. Most findings after round 1 were minors or problems that predate the diff. Implementers and every reviewer each ran the full test suites. The Workflow tool runs at most 2 agents at once per workflow on this 4-CPU machine, so in multi-lane workflows one lane's reviews waited for another lane's implementer.

1. **Bounded review loops that end on a review.** Each task has at most 3 rounds of implement, then two-lens review. Never stop on a fix that no reviewer has seen.
2. **Only substantive findings reopen a round.** A critical, major or minor finding reopens a round; a nit alone does not. Nits are fixed when a round is running anyway, or recorded. After the last round, remaining minors become tracked items: a TECHNICAL_DEBT entry, or an acceptance criterion with a named test on the owning plan task.
3. **Round 2 onward is a confirm review.** It covers only that round's commits and the earlier findings. New findings count only when those commits introduced them, or when they are critical or major anywhere. Unchanged code is not re-audited for minors.
4. **Design documents converge the same way.** Once an ADR has no critical or major finding, each remaining minor is fixed locally, made an implementation obligation (an acceptance criterion and test on the AG item), made an operator question (§13), or rejected with a reason. There is no open-ended re-review of the whole document; ADR-002 needed 10 revisions before this rule.
5. **Scope discipline.** Implementers do exactly the task's done-when and the review items: no new scope, no refactors beyond them. Reviewers flag scope creep as an issue (MISSION §12).
6. **Disk discipline.** Agents never copy the repository, build a second Rust target, or create extra venvs in the scratchpad. They run tests in the task worktree and compare with the base through `git show`/`git diff`. Budget about 2 GB per worktree that runs the full pytest (debug guard plus release bot-gateway). The orchestrator removes merged worktrees and finished agents' scratch.
7. **Never stop and resume a running workflow to change its prompts.** Resume reuses only the unchanged prefix of agent calls, so completed agents after the first changed call run again. Prompt changes apply to the next workflow.
8. **Lane balance.** Capacity allowing, from WAVE-6 on each wave includes, besides the security lane, at least one agent-journey task (M3: squads, memory, governed tools) and one design or UX task (M8: design system, accessibility).
9. **Gates per task, full gates per integration.** A task runs the gates its change touches (web-only tasks: web gates plus browser evidence, no pytest); the integration branch runs every CLAUDE.md gate once before the merge.
10. **Lean lane (the default from 2026-11-15).** One workflow per lane (the per-workflow cap is 2 concurrent agents). Each lane runs: implement → one review → one fix pass. The fix pass fixes every finding, nits included, without another review. Only a critical or major finding adds one confirm review, scoped to those findings. Problems that predate the diff and fall outside the Done-when go in the review's out_of_scope list, which the orchestrator triages into TECHNICAL_DEBT or the plan; they do not reopen the lane. Implementers and reviewers run only the tests of the modules they touch (plus lint and types); the full CLAUDE.md gates run once, at integration. Each approved lane merges on its own, without waiting for the rest of its wave. Script: `lean-lane` (`workflows/scripts/lean-lane-wf_367d777a-dce.js` in the session directory), launched once per lane with `args`.

## Environment facts

- Shared venv (2026-11-15 02:05): every worktree runs tests with the main checkout's `.venv`. After a merge that changes `uv.lock`, run `uv sync --locked` in the main checkout, or tests in every lane run against stale packages. Batch 2's first gate run failed 10 IDNA tests until the venv was synced to the wave-5 lock (yarl, urllib3, pillow and others).

- Cloud environment `koda` (personal): limited network (package registries + Google Fonts); `AGENT_TOKEN` / `ALLOWED_USER_IDS` set to CI dummy values in fresh sessions.
- 4 CPUs / 15 GB RAM: workflow subagent concurrency is effectively 2.
- PostgreSQL 16 + pgvector can be installed locally (`apt-get install -y postgresql-16-pgvector`); Docker is not available, so testcontainers-based fixtures skip.
- Parallel worktrees: the pytest conftest builds the Rust security service per checkout (~1.5 GB `rust/target` each). Waves share one service built from the main checkout (start `rust/target/debug/koda-security-service` once with `SECURITY_GRPC_TARGET=127.0.0.1:50300`) and delete worktree `rust/target` dirs after merge. Once M0-E2-T1 is on the branch, worktrees opt in with `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:50300` (an ambient `SECURITY_GRPC_TARGET` is ignored; without the opt-in each session starts its own guard on a private Unix socket). A shared guard runs the Rust build it was started from, so runs that change `rust/koda-security-*` must not use it. Disk headroom was 7.9 GB with 7 worktrees.
- Disk budget (2026-11-14 08:30): with ~20 worktrees the disk reached 96 %. Main consumers were Rust build output (main checkout 5.1 GB; each worktree that runs `cargo` ~1.5 GB, `--release` more) and agents' full-repo baseline copies in the scratchpad (0.7-2.6 GB each). Rules for agent prompts: prove fail-before on the same checkout rather than copying the repo, with a patch reverted and re-applied in the worktree (`git diff HEAD -- <files> > patch; git apply -R patch; <run>; git apply patch`), never `git stash` (see the next fact); build Rust only when the task touches Rust; delete worktree `rust/target` after merge. The main checkout keeps only `rust/target/debug/koda-security-service` (the shared guard binary); main-checkout test runs use `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:50300`. The shared guard runs as a harness background task with a 2 h limit and is restarted on the loop heartbeat. `tests/integration/conftest.py::cargo_build_release` builds `koda-bot-gateway` in release (~530 MB) once per checkout when the binary is missing, so non-Rust worktrees get a hard link to one prebuilt binary at `rust/target/release/koda-bot-gateway` (`../koda-wt/.shared-bin`).
- `git stash` is shared by every worktree of the repository (one `refs/stash`). On 2026-11-14 at 10:41, the AG-05 agent's `git stash pop` in `../koda-wt/AG-05` applied M0-E3-T2's stashed changes (`tests/fakes/telegram.py`, `test_agent_turn_e2e.py`, `test_scheduler_dispatch_postgres.py`). The agent noticed the conflict and set the foreign files aside, and M0-E3-T2 committed the same content at 10:41:59, so nothing was lost or merged into the wrong task (verified: both AG-05 commits touch only AG-05 files; M0-E3-T2's committed files are byte-identical to the set-aside copies). Agent prompts must not use `git stash` in parallel worktrees, and integration checks each task's diff for files outside its scope.
- Root cause of the "workflow journals pruned mid-run" and the lost task list seen earlier: the wipe under D-230. Workflow journals and transcripts live under `/root/.claude/projects/`, and every full `pytest` run on a pre-fix branch emptied `/root/.claude`. In-flight workflows keep running and notify, but can no longer be resumed from their journals.
- Until a worktree includes 6d050b5 (D-230), its full `pytest` run still empties the real `~/.claude` (this container's `/root/.claude` holds the agent harness's own state). Agent prompts for older branches must run tests with `HOME` pointing at a scratch directory. Integration branches merge main first.
- Shared test guard retired (2026-11-14 17:00). The harness stopped the shared guard on 127.0.0.1:50300 at its 2 h background limit, and a command that already ran with the longest allowed timeout is not restarted. From now on, agent prompts must not set `KODA_TEST_SECURITY_GUARD_TARGET`. Each pytest session starts its own guard on a private Unix socket (the default, through `cargo run`, about 1.5 GB of `rust/target` per worktree on first use). Workflows that were already running still pass the variable; if a run fails with the shared guard unreachable, it is rerun without it.
- Postgres here allows 100 connections. Parallel waves can exhaust them (`TooManyConnectionsError: sorry, too many clients already`); a failure with that error is capacity, not a defect. Rerun when load drops, and do not restart Postgres while agents run tests.
- Disk budget per worktree (2026-11-14 22:00): since M0-E2-T2 (56a87a6) every full pytest also builds `koda-bot-gateway` in release (~0.5 GB) besides the debug guard (~1-1.5 GB), so the hard-linked prebuilt binary no longer saves the build. Non-Rust waves share one `CARGO_TARGET_DIR` (`../koda-wt/.shared-target-w6`; the fixtures find binaries through cargo itself), which saves ~1.5 GB per worktree. Reviewers that copied the repository and built inside the copy pushed free disk to 1.6 GB on 2026-11-14 at 22:05. Rule 6 now applies to reviewer prompts too, and the orchestrator deletes a finished agent's scratch as soon as the agent-done monitor reports it.
- Orphaned processes (2026-11-14 18:55): five session guards from killed pytest runs and a reviewer's `node server.mjs` were still running, some for 9 h with deleted binaries held open (D-254). After each wave the orchestrator checks for `koda-security-service` and `node server.mjs` processes whose parent is init and whose sockets and ports nobody uses, stops them, and removes merged worktrees and finished review scratch dirs. This freed 7 GB on 2026-11-14 (6.9 → 14 GB free).
- Outbound web access is restricted: reference-product research relies on search results; anything not verifiable is marked as such.
- Shared Rust build directory (2026-11-15 03:27): cargo records path-crate sources with relative paths and judges them fresh by file times alone, so with one `CARGO_TARGET_DIR` a checkout whose files are older than another checkout's latest build silently reuses that build. Batch 4's first gate run errored on all 8786 tests because it reused the M5-E3-T8 lane's `koda-security-core` (no `redact_value`). Rules: the shared directory (`../koda-wt/.shared-target-w6`) serves only lanes whose `rust/` matches main; a lane that changes `rust/` passes `target: ../koda-wt/.target-<id>` to the lane script; integration gates use `../koda-wt/.target-int` and touch the checkout's Rust sources first (`int-gates.sh`). After any `rust/` merge, rebuild the shared guard once from a main-based checkout with its Rust sources touched.
- Container restarts stop every background task (workflows, monitors, gate runs) and Postgres. Recovery: `service postgresql start`; resume each workflow with its original `args` and `resumeFromRunId` (completed agents replay from cache; the interrupted agent reruns, so save and restore any half-finished edit in its worktree first); re-arm the monitors.

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

- DEFECT-BATCH-1 — seven verified high/critical defects fixed and merged (a4a441e): D-001/D-016 scheduled jobs, D-003 SSRF guard, D-004 login rate limiting, D-009 `/cancel`, D-018 password recovery, D-020 circuit breakers, D-022 event-stream resume. Two independent review rounds plus an integration review; full gates on the merged tree. Plan tasks M1-E3-T1, M3-E8-T1 and M3-E8-T2 are done. M1-E1-T2, M3-E1-T1, M3-E1-T2, M3-E2-T1 and M3-E7-T1 are `in-review` (corrected 2026-11-14: each done-when names a live journey replay or a characterisation test that has not landed yet, so MASTER_PLAN §3 rules out `done`; each task's evidence line names what is missing); FEATURE_MATRIX: 8 features left `broken`. Evidence: `VALIDATION_REPORT.md`.

- WAVE-2B — six tasks merged (6d050b5). M1-E8-T1, AG-04 and AG-05 are done. AG-02 is implemented and its contract check passes against the pinned binaries; the image builds and the first CI run of the `provider-cli-contract` job are still unverified (no Docker here). M1-E1-T3 and M1-E8-T3 were completed by LIVE-REPLAY-1. The integration review and two independent verification rounds found minors, lows and one high data-loss defect (D-230: disconnect emptied whole CLI folders, and tests wiped the real `~/.claude`). All were fixed on the branch with fail-before tests (63e92fe, 7076bb0, 73cab78, 8c35b0c, b835384). Evidence: `VALIDATION_REPORT.md` "WAVE-2B".

- LIVE-REPLAY-1 — J-01, J-03, J-07, J-15 and the M1-E8-T3 placeholder checks were replayed live on dfa596c, natively without Docker, and re-run independently: all work. M1-E1-T2, M1-E1-T3, M3-E7-T1 and M1-E8-T3 are now `done`. Found: D-136 confirmed at runtime (medium, M1-E1-T13), the known D-03, D-07, D-09, D-10 and D-12, and new low defects D-231..D-237. Evidence: `VALIDATION_REPORT.md` "LIVE-REPLAY-1".

- WAVE-3 — nine tasks merged (9296448). Done: M1-E3-T8, M0-E3-T1, M0-E3-T9, M3-E2-T6, M0-E2-T2, M0-E2-T3, M0-E2-T8, M0-E3-T6 and M1-E1-T17. M1-E1-T16 is `in-review` until the CI docker smoke runs. D-225's root cause is measured: leaked bridge-loop pools. The integration verified the clean merges, fixed the AG-05 fixture pool leak and three leftovers, and recorded D-238..D-251 as follow-ups. Gates: 6360 passed, 63 %; Postgres 270 passed. Evidence: `VALIDATION_REPORT.md` "WAVE-3".

## Active tasks

(2026-11-15 05:30 UTC. The progress tracker mirrors this list for the operator.)

- Integration batch 5 merged: SEC-D269, M10-E1-T2, M9-E1-T4 + M9-E2-T1/T2, M2-E2-T1 (+ T5 in review), M3-E4-T6, M3-E6-T1/T2/T3, M8-E1-T1/T2/T3.
- Approved, waiting for integration batch 6:
  - SEC-D283 (D-283 single-use codes, D-284, D-285), then SEC-D294 (D-294 one owner, D-295) on top of it.
  - SEC-D292 (D-292 hash once and load those bytes, D-291).
  - M1-E5-T1 + M1-E5-T4 squad authorization, then SQ-D304 (D-304, D-306) on top of it.
  - M1-E3-T6 + M1-E4-T6 + M1-E5-T3 (OAuth redirect, MCP isolation settings, channel pairing limits).
  - M6-E3-T2/T4 + M6-E1-T5/T8 (provider ids, /curl alias, grounding gate, runtime terminal).
  - FIX-D293 (/cancel on Postgres).
  - M5-E3-T8 one redactor with linear-time patterns (changes `rust/` and `proto/`; Rust gates on `../koda-wt/.target-int`).
- Lean lanes running: FIX-D276 (D-276 runtime root isolation, D-277 routine editor Escape), SEC-D300 (D-300, D-301), M6-D296 (D-296, D-297, D-298).
- Awaiting the operator: ADR-002 OQ-1..OQ-12 and plan Q-25..Q-31; the web Docker image build; shellcheck for `scripts/install.sh`; actionlint and a first GitHub Actions run of `migrations-gate.yml`.

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
- `CHANGELOG.md` was the changelog of an unrelated project; M1-E7-T6 replaced it with Koda's own, starting at 1.0.18.
- Web build had one transient Turbopack `next/font/google` resolution failure (passed on retry); watch for recurrence.

## Blocked tasks

_None._ (GitHub push access restored 2026-11-14; branch `claude/dreamy-cerf-mhvbwn` pushed.)

## Discovered regressions

_None._ Note: test runs sharing the machine with audit agents must use their own database. A shared run produced 111 spurious failures when another session's security-guard service on port 50065 went away; M0-E2-T1 removes that failure mode.
