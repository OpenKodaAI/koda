# Validation Report

Evidence log for completed tasks. Each entry lists the exact commands run and
their observed results. Environment notes: local PostgreSQL 16 + pgvector;
runs that share the machine with audit agents use a dedicated database. Until
M0-E2-T1 the test session attached to any security-guard service already
listening on `SECURITY_GRPC_TARGET` (default port 50065), so earlier entries use
a dedicated port; since M0-E2-T1 each session starts its own guard on a private
Unix socket unless `KODA_TEST_SECURITY_GUARD_TARGET` opts into a shared one.

## P0-FIX-CARGOFMT — documented Rust format gate

- `cargo fmt --all --check --manifest-path rust/Cargo.toml` → rc=0
- `pytest tests/test_installation_assets.py tests/test_top_tier_roadmap_assurance.py` → 41 passed

## M0-PG-FIXTURES — make the Postgres suite runnable and run it in CI

Problem: all 188 `@pytest.mark.postgres` tests skipped everywhere (CI sets no
`POSTGRES_TEST_DSN`; `testcontainers` is not a dependency). With a DSN they
produced 47 errors and 43 failures.

Root causes and fixes:

| Symptom | Root cause | Fix |
|---|---|---|
| 47 errors: `cannot truncate a table referenced in a foreign key constraint` | Five squad test files kept divergent per-file `TRUNCATE` lists that predate `squad_reply_obligations` | Single `reset_squad_runtime_tables()` helper in `tests/postgres_fixtures.py` truncating all squad runtime tables in one `TRUNCATE ... RESTART IDENTITY CASCADE` |
| 43 failures: `primary_backend_unavailable ... KNOWLEDGE_V2_POSTGRES_DSN is empty` | Only the testcontainers path exported the DSN | Autouse `_postgres_dsn_scope` fixture sets the DSN for postgres-marked tests |
| 4 unrelated failures (`tests/test_utils/test_pending_approvals.py`) once the DSN was exported | DSN leaked for the whole session (global `os.environ` write plus `importlib.reload(koda.knowledge.config)` in two integration tests), switching later tests to the shared database | DSN scoped per test; `KNOWLEDGE_V2_*` constants restored and shared backend cache cleared after each postgres test |
| Never exercised in CI | No job provided a database | New `python-postgres-tests` job (pgvector service) in `.github/workflows/pr-quality.yml` |

Evidence (all with `AGENT_TOKEN=test-token ALLOWED_USER_IDS=123456789`):

| Command | Result |
|---|---|
| `POSTGRES_TEST_DSN=... pytest -m postgres` (run twice) | 186 passed, 2 skipped (both runs) |
| `POSTGRES_TEST_DSN=... pytest` (full suite, isolated DB + security port) | 5059 passed, 15 skipped (optional deps: faiss, sentence-transformers, opt-in e2e) |
| `pytest` (full suite, no DSN) | 4874 passed, 200 skipped — identical to baseline |
| `KODA_SKIP_SECURITY_GUARD_SERVICE=1 ... pytest -m postgres` | 24 failed → the CI job must keep the security guard service (it does) |
| `actionlint .github/workflows/pr-quality.yml` | clean |
| `ruff check` / `ruff format --check` on changed files | clean |
| `scripts/sync_npm_readme.py` | no drift |

Independent review (subagent, re-ran all checks on its own DB): **approved**, one major issue.
The DSN could still leak in partial runs, because `koda.services.audit`, `koda.control_plane.manager`
and `koda.knowledge.v2.common` copy the constant at import time; if a postgres test triggers
that first import, the copy persists. Fixed: the fixture now patches every loaded `koda.*`
copy during the test and resets copies imported or reloaded during the test afterwards; the
shared-backend cache is imported before patching. Minor items fixed: exact marker matching
(`get_closest_marker`, also in the collection hook) instead of keyword matching; stale
docstrings and redundant `importlib.reload` / no-op `_SHARED_BACKENDS` cleanups removed from
three integration tests; `test_postgres_message_bus.py` uses the shared truncate helper;
`docs/squads/operations.md` no longer tells people to export the DSN twice.

Post-review evidence:

| Command | Result |
|---|---|
| Reviewer's leak probes (`leakcheck`, `auditprobe`) on `test_threads.py`, `test_coordinator.py`, `test_runtime_postgres_isolation.py` + `test_pending_approvals.py` | no leaked DSN copies, env, or cached backends; audit backend disabled after the session |
| `pytest -m postgres` with DSN | 186 passed, 2 skipped |
| full suite with DSN | 5059 passed, 15 skipped |
| full suite without DSN | 4874 passed, 200 skipped (baseline) |
| `tests/test_postgres_fixture_smoke.py` | extended with a negative case (keyword-only item is not skipped); passes |

Follow-ups (not done here):
- Make `python-postgres-tests` a required status check (repository settings; operator action).
- `_build_store` in the runtime isolation/extended tests permanently sets `koda.config.AGENT_ID` and reloads `postgres_store` (pre-existing; harmless in the current suite).
- The new CI job has not run yet (push blocked).

## SEC-PLACEHOLDER-SECRETS — publicly known placeholder credentials

Vulnerability (verified in code by the orchestrator): `docs/install/local.md` instructed
`cp .env.example .env && docker compose up`, leaving `CONTROL_PLANE_API_TOKEN=replace-with-a-random-token`;
`OperatorAuthService.resolve_bearer_token` accepted it as a break-glass credential carrying the
owner identity, on port 8090 published on all interfaces by `docker-compose.yml`. Same pattern for
`RUNTIME_LOCAL_UI_TOKEN` and `WEB_OPERATOR_SESSION_SECRET`. The packaged installer was not affected.

Fix: `koda.config.is_placeholder_secret` / `_env_secret`; `settings.parse_api_tokens` drops placeholders;
runtime-token broker refuses to sign with one; supervisor logs why at startup; web treats a placeholder
session secret as unset and checks it before contacting the control plane (login + owner registration);
`scripts/generate_env_secrets.py` for manual installs (new install: all placeholders; existing: auth only
unless `--all`; 0600 via mkstemp + atomic replace); doctor placeholder checks case-insensitive;
CI docker smoke uses the generator.

| Command | Result |
|---|---|
| `pytest` (full, no DSN) | 4895 passed, 200 skipped (baseline 4874 + 21 new tests) |
| `pnpm test:web` | 157 files, 692 tests (baseline 686 + 6 new) |
| new web tests against old code | placeholder-secret test and register-owner pre-flight test fail without the fix |
| `ruff check` / `ruff format --check` / `mypy koda/` | clean |
| `pnpm lint:web` | 0 errors, 40 warnings (unchanged) |
| `pnpm build:web` | pass (one transient Turbopack next/font failure earlier, passed on retry) |
| generator on real `.env.example` + `doctor.py --strict` | three strong-secret checks pass; raw `.env.example` fails them |

Reviews: independent security reviewer, two rounds. Round 1 request changes (re-running the docs
snippet rotated the Postgres password; web threw after owner registration, losing recovery codes; plus
6 minor) → fixed. Round 2 approve with 4 minor (default mode rotated storage keys on existing installs;
fixed temp name followed symlinks; narrower placeholder detection; login echoed the internal error) → fixed
with tests. Deferred items are listed under "Pending findings" in `EXECUTION_STATUS.md`.

## DATA-UNINSTALL-VOLUMES — `koda uninstall` deleted all data without `--purge`

Defect (skeptic-confirmed, reproduced): `uninstallCommand` always ran `docker compose down -v`, deleting
the Postgres, object-storage and state volumes even without `--purge`, contrary to the help text, the
reinstall guard comment and `docs/install/local.md`.

Fix (`packages/cli/bin/koda.mjs`): plain uninstall runs `down --remove-orphans`, keeps volumes and `.env`,
and points to `koda up`; `--purge` checks Docker is reachable, removes volumes via `resetManagedVolumes`
(compose `down -v` with a project-label fallback that also catches volumes from older releases), then
deletes the install directory; any directory without `bundle/docker-compose.release.yml` or
`manifest.json` is refused (previously `koda uninstall --dir ~ --purge` would `rm -rf` the home dir).
Help text and both READMEs document the semantics.

| Command | Result |
|---|---|
| `tests/test_cli_uninstall.py` (real CLI + fake `docker` recording argv) | 3 passed; the no-purge test fails against the old CLI |
| hygiene/docs/install-asset tests | 46 passed |
| full `pytest` | 4897 passed, 200 skipped (before the guard test) |
| `node --check packages/cli/bin/koda.mjs`, `scripts/sync_npm_readme.py` | ok, no drift |

Review: independent reviewer approved (simulated install → uninstall → install keeps the identical `.env`
and skips the volume guard; release smokes still use `--purge`). Its minor items 1–3, 5–7 are fixed here;
item 4 (default project name `koda` collides with a source checkout named `koda`) is recorded as a follow-up.

## NET-LOOPBACK — publish the dashboard and control-plane API on loopback by default (operator-approved)

Problem: `docs/install/vps.md` promised loopback-only publishing, but `docker-compose.yml` and the
packaged `docker-compose.release.yml` published 8090/3000 on all interfaces, and the prod overlay only
added loopback mappings (Compose concatenates `ports`). Non-default `CONTROL_PLANE_PORT` also broke the
stack (container listened on the custom port while the mapping and `http://app:8090` assumed 8090).

Fix: API `127.0.0.1:${CONTROL_PLANE_PORT:-8090}:8090` (no opt-out); dashboard
`${WEB_PUBLISH_ADDRESS:-127.0.0.1}:${WEB_PORT:-3000}:3000`; container always listens on 8090 and
`CONTROL_PLANE_PUBLIC_PORT` carries the host port for the OAuth relay URL; prod overlay no longer repeats
ports; `.env.example` `CONTROL_PLANE_BIND=127.0.0.1` for native runs; nginx sample proxies to
`127.0.0.1`; migration note, VPS/local/Tailscale/observability/hardening/cluster docs and config
reference updated; release CHECKSUMS regenerated.

| Command | Result |
|---|---|
| `tests/test_compose_port_exposure.py` (new contract: loopback defaults, `:-` only, no overlay re-publishing, no host networking, fixed internal port, relay URL) | pass; fails against the old compose files / provider_auth |
| `tests/test_installation_assets.py` (tarball guard now structure-aware) | pass |
| full `pytest` | 4920 passed, 200 skipped |
| `ruff` / `ruff format --check` / `mypy koda/` / actionlint | clean |
| `scripts/release_metadata.py` | no drift |
| reviewer `docker compose config` (base, +prod, +dev, +cluster, release) | app → 127.0.0.1:8090, web → 127.0.0.1:3000, no duplicates |

Review: independent reviewer, round 1 request changes (2 major docs issues: silent `koda update` behaviour
change; plain-HTTP LAN advice incompatible with Secure cookies; plus minors) → all addressed; round 2 **approve**: the reviewer re-rendered `docker compose config` for base, +prod, +dev, +cluster and release with `CONTROL_PLANE_PORT=18090` (host 127.0.0.1:18090 → container 8090, web → app:8090, no duplicate bindings) and ran 162 related tests. Round-2 minors fixed in `52ffc26`: `cluster_smoke.sh` probes the fixed internal port; tailnet-IP guidance removed (plain HTTP over a tailnet still drops Secure cookies; use `tailscale serve --bg`); stale compose comments; a remote proxy reaches only the dashboard; `CONTROL_PLANE_PUBLIC_PORT` documented in `.env.example`.
Follow-up: cluster overlay `replicas: 3` with a fixed host port (pre-existing).

## M0-E2-T1 — isolate the security-guard fixture (D-175, TD-121 part)

Root cause: `tests/conftest.py` attached to any gRPC listener already on
`SECURITY_GRPC_TARGET` (default `127.0.0.1:50065`), so concurrent sessions used
each other's guard (111 spurious failures when one went away) and a stale build
could mask regressions.

Change: `tests/_security_guard.py` + `tests/conftest.py`. Each session pins
`SECURITY_GRPC_TARGET` (before `koda.config` is imported) to a Unix socket in a
fresh `0700` temp directory and runs its own guard there; an ambient value is
ignored. `KODA_TEST_SECURITY_GUARD_TARGET` is the explicit opt-in to a shared
guard (fails if unreachable). The fixture fails if `koda.config` was imported
before the pin, stops the guard on every exit path (including
`KeyboardInterrupt`), reports startup failures with the cargo log tail, and
without `cargo` skips with an "ALL TESTS SKIPPED" banner (fails under `CI`).
Docs: `CONTRIBUTING.md`.

Review: independent QA/simplification review → approve with 11 minor/nit
items. Main item (a narrow port race could still attach to a foreign server;
the retry loop handled only the harmless case) resolved by switching to a
per-session Unix socket, which removed the port picking, retry and retarget
code. Other items fixed: cleanup on `BaseException`, dedicated `CargoMissing`,
cargo output no longer suppressed, readiness polled on fresh channels through
`resolve_grpc_target`/`create_grpc_channel`, loud skip banner, config pin check,
stale-build warning for shared guards, engineering-doc references updated.

| Command | Result |
|---|---|
| Two concurrent `pytest -q -p no:cacheprovider` full runs in one checkout, with `SECURITY_GRPC_TARGET=127.0.0.1:50065` exported and a decoy gRPC server listening on 50065 | both **4928 passed, 200 skipped** (48 s each); no `/tmp/koda-guard-*` left |
| `SECURITY_GRPC_TARGET=127.0.0.1:50065 pytest tests/test_security_guard_fixture.py tests/test_services/test_security_guard.py tests/test_services/test_provider_env.py tests/test_control_plane_supervisor_env.py` | 27 passed |
| same fixture + guard tests with `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:50300` (shared) | 18 passed |
| `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:1` | session fails: "…is not reachable: security guard did not listen…" |
| fixture tests with `cargo` removed from `PATH` | 8 skipped + "ALL TESTS SKIPPED" banner with the reason |
| `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` | pass / 710 files formatted / no issues in 358 files |
| `pytest tests/test_public_docs.py tests/test_open_source_hygiene.py tests/test_installation_assets.py tests/test_top_tier_roadmap_assurance.py` | 51 passed |

## M0-E4-T1 — dependency advisory triage

Raw data collected by the orchestrator on 2026-11-14 (scratchpad, not committed):

| Command | Result |
|---|---|
| `uv export --locked --no-hashes --all-extras` then `uv run pip-audit -r … --no-deps --disable-pip -f json` | 144 packages audited; 14 vulnerable; 206 records (157 GHSA after alias dedup) |
| `pnpm audit --json` / `pnpm audit --prod --json` | 5 critical, 41 high, 39 moderate, 8 low / 5, 17, 12, 2 |
| RustSec advisory-db (`git clone --depth 1`) matched against `rust/Cargo.lock` and `rust/koda-command-guard/Cargo.lock` by a local semver matcher (`cargo-audit` could not be installed in this session) | 29 findings in 17 crates; matcher independently re-checked 29/29 by the Rust analyst |
| GitHub advisory records for the Python GHSA aliases (sparse clone of `github/advisory-database`) | 157/157 fetched, severity source for Python |

Triage workflow `wf_d4d7a684-2ed` (20 agents): one analyst per slice (Python, Node prod, Node dev, Rust), a skeptic per critical/high non-upgrade claim, a registry feasibility check per slice, and a report writer. 34 verdicts; 3 overturned (urllib3 and postgres-protocol reachable after all; cryptography's full fix needs 50.x). Output: `docs/engineering/SUPPLY_CHAIN_TRIAGE.md`. Orchestrator spot-check: the `--no-dev` claim (D-224) reproduced by diffing `uv export` with and without `--no-dev`.

Limitation: Dependabot's alert list could not be exported (no API access from this session), so its 352 alerts are compared by count only.

## DEFECT-BATCH-1 — seven verified high/critical defects (merged a4a441e)

Process: workflow `wf_1ddc4a95-938` (21 agents) implemented each fix in its own worktree with tests written first and shown to fail on the pre-fix code, then an independent review and an address round. Workflow `wf_4962a220-f9b` (22 agents) then re-reviewed each final branch from scratch (two lenses — security/correctness plus test adequacy — for D-003, D-004 and D-022), ran bounded address/re-review rounds, and reviewed the merged `integrate/batch-1` for cross-branch interactions. All seven branches were approved; the integration review's findings (stale merge, `vps.md` rate-limit figures, `not_running` contract) were resolved before the merge.

| Defect | Plan task | Fix | Review |
|---|---|---|---|
| D-001 / D-016 | M3-E1-T1, M3-E1-T2 | Automatic and web-created scheduled jobs run; stale policy snapshots are refreshed with a compare-and-swap update and a `job.policy_snapshot_refreshed` event; create replay keeps `message`/`validation_run_id` | round 1 approve (5 minor → fixed), round 2 approve |
| D-003 | M1-E3-T1 | SSRF guard: unmapped IPv4-mapped IPv6, `0.0.0.0/8`, `100.64.0.0/10`, connect to the validated IP; the pre-check now uses the host aiohttp connects to (IDNA mismatch found in round 2); yt-dlp only sees canonical watch URLs; `.env` provider base URLs count as operator overrides | round 1 request_changes → fixed; round 2 request_changes (major: IDNA host mismatch) → fixed; round 3 approve |
| D-004 | M1-E1-T2 | Per-real-client login buckets; `X-Forwarded-For` trusted only from configured proxies; the dashboard server rewrites XFF; IPv6 per /64; bounded dashboard windows | round 1 request_changes → fixed; round 2 request_changes (major) → fixed; round 3 approve |
| D-009 | M3-E2-T1 | `/cancel` and the runtime cancel/interrupt stop queued and running light tasks; a finished task answers `409` with `action: "not_running"` | approve (minor items fixed twice) |
| D-018 | M3-E7-T1 | Recovery codes canonicalized on both sides (non-ASCII dropped before upper-casing; no browser upper-casing) | approve (minor items fixed twice) |
| D-020 | M3-E8-T2 | Open breakers recover through a half-open probe with a fresh timeout; each transition audited | approve twice |
| D-022 | M3-E8-T1 | SSE and WS resume past event id 1000 with validated cursors; relay reconnects on transient failures | round 1 request_changes → fixed; round 2 approve (minor → fixed) |

Gates on `integrate/batch-1` e65bb32 (the merge adds only docs/engineering commits on top):

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` | pass / 712 files formatted / no issues in 358 files |
| `KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:50300 pytest --cov=koda` | 5164 passed, 205 skipped; 62 % line coverage (baseline 61 %) |
| `POSTGRES_TEST_DSN=… pytest -m postgres` | first run 189 passed / 2 failed (`test_squads/test_projections.py`, load average ~10); 4 reruns (two consecutive on a fresh database, two on the original) 191 passed / 2 skipped — filed as D-225 / M0-E2-T8 |
| `pnpm lint:web` / `pnpm test:web` / `pnpm build:web` | 0 errors (40 pre-existing warnings) / 169 files, 783 tests passed / ok |
| Branch-level full suites (each worktree) | every branch passed its own full suite; fail-before evidence recorded per branch in the workflow results |

Follow-ups filed from the agents' notes: D-220 (bundled nginx config, M1-E1-T16), D-221 (setup codes, M1-E1-T17), D-004 remainder (429 message, M1-E1-T18, ADR-038), D-222 (env-backed cancel, M3-E2-T6), D-223 (remaining outbound fetch paths, M1-E3-T8), D-225 (projection test flake, M0-E2-T8).

Not verified here (no Docker): live browser journeys J-07 (password recovery) and the routine wizard, and the docker smoke. These stay open in the task evidence above.
