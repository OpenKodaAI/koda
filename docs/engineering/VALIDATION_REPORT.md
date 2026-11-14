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

## WAVE-2B — six plan and ADR-002 tasks (merged 6d050b5)

Process: workflow `wf_f6f3c9f3-4d8` implemented each task in its own worktree (`task/<id>` from `integrate/batch-1`). Each task wrote its tests first and showed them failing on the pre-change code, then went through two independent review lenses and a bounded address and re-review loop (at most three rounds). The orchestrator merged the six branches on `integrate/wave-2b`, ran the full gates and an integration review (approve, with minor findings). It then fixed every minor finding on the branch, each with a fail-before test (63e92fe, 7076bb0), and had the fixes reviewed independently.

| Task | Addresses | Change | Review |
|---|---|---|---|
| M1-E8-T1 | D-006 (interim), F-SCH-09, R-53 | The routine read-only and allowed-paths controls are disabled and labelled "Not enforced yet" in five locales. Stored values are shown and kept on save. | round 1 minor (edit-mode cases for empty and malformed payloads) → fixed |
| M1-E8-T3 | D-007 (remainder, interim), F-PLT-07 | Placeholder Postgres and S3 secrets: a warning at every start, a failing doctor check with the rotation command, and an operator-only API behind the dashboard banner. | round 1 follow-ups (`export` lines, every placeholder form, banner placement) → fixed |
| M1-E1-T3 | D-050, D-193, D-226, R-36, F-SET-16 | Pre-login `onboarding/status` returns `{has_owner, bootstrap_required}`. `auth/status` hides `recovery_available` from anonymous callers, and hides the bootstrap path and loopback flag once an owner exists. Readiness checks come from live state. | round 1 (auth/status flags) → fixed |
| AG-02 | ADR-002 | Provider CLIs pinned in one npm lockfile installed by both images; a contract table; probes that fail closed; no npx fallback. | round 1 (six minors) → fixed |
| AG-04 | ADR-002 §2.4 L1 | The worker and the runtime kernel are non-dumpable with a zero core limit, and refuse to start otherwise. The Python startup window is recorded as a residual that AG-14, AG-15 and AG-16 close together. | rounds 1 and 2 → fixed |
| AG-05 | ADR-002, R-07 | Fail-closed master key with a Postgres fingerprint. On upgrade the key is checked against stored ciphertext before it is recorded, and an explicit operator file handles the lost-key path. | round 1 (upgrade path) → fixed |

Integration review findings, fixed on the branch:

- **Master key mode.** `_tighten_permissions` changed only modes numerically above `0o600`, so `0o440`, `0o444`, `0o404` and `0o604` kept group or other read access. It now removes every group and other bit, and logs `control_plane_master_key_permissions_too_open` when chmod is refused. Fail-before: 4 of the new cases fail on 62b6129.
- **Gemini argv.** gemini-cli parses with yargs, which reads a separate value starting with `-` as an option. Checked against the pinned gemini-cli 0.68.0 with an isolated HOME and no credentials:
  - `--prompt -y --approval-mode=default` fails with "Not enough arguments following: prompt", because `-y` was taken as `--yolo`;
  - `--prompt=-y --approval-mode=default` gets through parsing to the auth check.

  The Gemini contract now requires attached values, and the runner and the subscription-login probe emit them. The probe used `-p`, which is not in the contract (AG-02 acceptance: "the builders cannot emit a token that is not in the contract"). Fail-before: `-p is not in the contract for root`.
- **`CODEX_BIN`.** It is now one executable path, as `GEMINI_BIN` already was. `resolve_provider_command("codex")` shlex-split it, so extra tokens became argv the contract never checked, while the Codex runners used the whole value as `argv[0]`. Fail-before: 3 cases.
- **Public control-plane paths.** They now match exactly in the backend, as they already did in the dashboard. A route added under a public path no longer skips auth. Fail-before: `/api/control-plane/auth/password/recover/` was public.
- **Test leak.** A new Gemini runner test patched `resolve_provider_command` a second time with `monkeypatch` while the module's autouse `patch` was active. The conftest's autouse fixture held `monkeypatch`, so its undo ran after `patch` exited and restored the mock: 6 order-dependent failures. The redundant patch was removed.

A second independent review of those fixes found nothing critical or high, and eight low findings and nits. All of them are fixed in 73cab78, each with a test shown to fail first:

- **One resolver for the provider executable.** `provider_auth.provider_executable()` reads a non-empty `*_BIN` from `base_env`, then `koda.config` (stripped, honouring the `{AGENT_ID}_` prefix), then the CLI name. Every runner, probe and status view uses it. Before, the Gemini runner path ignored `GEMINI_BIN` from the process environment, and `config.CODEX_BIN` was neither stripped nor defaulted. Checked against the pinned binaries: with `gemini` and `codex` off `PATH` and the two settings pointing at them, the contract check passes for all three CLIs.
- **`resolve_provider_command()` accepts only the local CLI providers.** HTTP providers such as `perplexity` and `openrouter` used to fall through to the Gemini branch and resolve to `gemini` (fail-before: 2 cases).
- **Public routes.** The auth middleware decides on the resolved route (resource and method), not the path string. A later `/auth/{name}` pattern, a `GET` beside a public `POST`, or an encoded slash (`auth%2Fstatus`) that resolves elsewhere now needs a session. Fail-before: 2 middleware cases. A test also checks the public methods against the registered routes.
- **Master key mode.**
  - chmod only removes group and other bits.
  - The mode is read again afterwards, so a mount that accepts chmod but keeps the mode is reported.
  - The warning is logged once per file and mode.

  Fail-before: 5 cases.
- **`validate_args`.** Attached and separate values share one value check, so a future attached-values contract keeps the config-key allowlist. The legacy-token guard now splits attached values (the old guard missed `--approval-mode=plan` and `--prompt=x`). The Gemini login-probe test now fails if the probe stops checking its own command line.

The same reviewer then verified 73cab78. All eight findings were resolved, and its probes of the real 442-route router found nothing public beyond the six routes and their methods. It found one regression and a related pre-existing gap, both fixed in the next commit with tests shown to fail first:

- **medium, regression:** `resolve_provider_command()` now raises `KeyError` for HTTP providers. `provider_logout_command` resolved before checking for a logout, so disconnecting an HTTP provider answered 404 and left its stored API key in place. Disconnecting Gemini already failed the same way when the CLI was missing, and so did ElevenLabs.
- **low, pre-existing:** `verify_provider_subscription_login` sent every provider except Claude and Codex to the Gemini probe, so verifying an HTTP provider in subscription mode would have run a real Gemini model call.

The fix:

- One set, `SUBSCRIPTION_LOGIN_PROVIDER_IDS` (claude, codex, gemini), gates the login, logout and verify flows before anything is resolved.
- Only Claude and Codex have a logout subcommand.
- A missing CLI is reported, not raised, so a disconnect still wipes stored credentials.
- Fail-before: 9 of 10 new cases. The disconnect test runs the real logout with no mock.
- Nits: `clear_fernet_cache` no longer re-arms the key-mode warning (`ensure_master_key` calls it at every start; fail-before: two warnings), and the ADR note now quotes the observed rejection.

A fresh reviewer verified 8c35b0c. It ran the real disconnect path for every HTTP provider, ElevenLabs, Gemini and Ollama, and the real login sessions with fake CLIs, and confirmed the four findings fixed. It also found a data-loss defect, recorded as **D-230 (high)**:

- **What it did.** Disconnecting Claude, Codex or Gemini emptied the CLI's whole folder (`$HOME/.claude` or `CLAUDE_CONFIG_DIR`, `.codex` or `CODEX_HOME`, `.gemini`). On a native install that folder is the operator's own CLI configuration.
- **What it did here.** Three tests ran the wipe against the real HOME, so every full `pytest` run emptied the contributor's `~/.claude`. That includes this container's `/root/.claude`, which the reviewer found holding only `projects/`.
- **Fixed in the merge commit's last fix:**
  - Only the credential files the pinned CLIs use are removed: Claude `.credentials.json`; Codex `auth.json`; Gemini `oauth_creds.json`, `google_accounts.json` and `mcp-oauth-tokens.json`. Each name was found in the pinned CLI bundles and binaries.
  - `tests/conftest.py` gives every test its own empty HOME, with `CLAUDE_CONFIG_DIR` and `CODEX_HOME` unset and the Rust toolchain paths pinned.
  - Fail-before: 4 wipe cases and the HOME test.
  - After a full run, `/root/.claude` still holds `projects`, `session-env` and `skills`.
- **Also fixed:**
  - Disconnect now resets a provider to its fresh-install mode (HTTP providers to `api_key`, not `subscription_login`).
  - A missing CLI at disconnect is no longer stored as `last_error`, because `ProviderLogoutResult.attempted` separates "no CLI to run" from "the logout ran and failed".
  - Starting a login without the CLI answers 400 with "CLI is not installed" instead of 500 (fail-before: 3 cases).
  - `provider_supports_subscription_login` reuses the one provider set.
  - CONTRIBUTING and the API reference say what tests and disconnect touch.

Gates:

| Tree | Command | Result |
|---|---|---|
| 62b6129 (six branches merged) | `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` | pass |
| 62b6129 | `pytest --cov=koda` (shared guard) | 5348 passed, 224 skipped; 62 % |
| 62b6129 | `pytest -m postgres` | 210 passed, 2 skipped |
| 62b6129 | `pnpm lint:web` / `pnpm test:web` / `pnpm build:web` | 0 errors (40 pre-existing warnings) / first run 813 of 814 (`sessions/page.test.tsx` timeout under load, D-229), rerun 814 passed / ok |
| 62b6129 | `cargo fmt --all --check` / `cargo clippy … -D warnings` / `cargo test --workspace` | pass / pass / pass |
| 7076bb0 (review fixes) | `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` | pass / 720 files formatted / no issues in 360 files |
| 7076bb0 | `pytest --cov=koda` (shared guard) | 5366 passed, 224 skipped; 62 % |
| 7076bb0 | master-key Postgres tests (`-m postgres`, fingerprint and key files) | 19 passed in three consecutive runs. One earlier run failed with `TooManyConnectionsError`: the parallel waves had used up the 100-connection server. |
| 7076bb0 | `tests/test_open_source_hygiene.py` | 5 passed |
| 7076bb0 | vitest on `src/proxy.test.ts` and `src/lib` (public-path consumers) | 55 files, 340 tests passed |
| 7076bb0 | `python -m koda.services.provider_cli_contract` against the pinned binaries (`claude` 2.1.325, `codex` 0.169.0, `gemini` 0.68.0; isolated HOME, no credentials) | `ok: true` for all three, versions match, nothing missing |
| 7076bb0 | `tests/security/test_process_hygiene.py` (real entrypoint, throwaway uid, dumpable control) | 10 passed |
| 73cab78 (second review fixes) | `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` | pass / 720 files formatted / no issues in 360 files |
| 73cab78 | `pytest --cov=koda` (shared guard) | 5387 passed, 224 skipped; 62 % |
| 73cab78 | master-key Postgres tests / `tests/test_open_source_hygiene.py` | 19 passed / 5 passed |
| 73cab78 | `python -m koda.services.provider_cli_contract` against the pinned binaries, once on `PATH` and once only through `GEMINI_BIN` and `CODEX_BIN` | `ok: true` for all three both times |
| 8c35b0c (provider-flow fixes) | `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` | pass / 720 files formatted / no issues in 360 files |
| 8c35b0c | `pytest --cov=koda` (shared guard) | 5397 passed, 224 skipped; 62 % |
| 8c35b0c | master-key Postgres tests / `tests/test_open_source_hygiene.py` | 19 passed / 5 passed |
| b835384 (D-230 and login fixes) | `pytest --cov=koda` and `pytest -m postgres` with per-test HOME isolation | 5401 passed, 224 skipped, 62 %; Postgres 210 passed, 2 skipped (fresh database) |
| b835384 | `ruff check .` / `ruff format --check .` / `mypy koda/ --ignore-missing-imports` / full `pytest --cov=koda` / hygiene | pass / 720 files formatted / no issues in 360 files / 5404 passed, 224 skipped, 62 % / 5 passed |
| 6d050b5 (merge) | the merge adds nothing on top of b835384; web and Rust files are unchanged since the 62b6129 gates | — |

Incident recorded in EXECUTION_STATUS: `git stash` is shared by every worktree, and the AG-05 agent's `stash pop` applied M0-E3-T2's stash. Nothing was lost or mixed into the wrong branch (both AG-05 commits touch only AG-05 files, and M0-E3-T2 committed byte-identical content). Agent prompts now revert and re-apply a patch instead.

Not verified here (no Docker): the image builds that install the pinned CLIs, and the docker smoke. The first CI run of the `provider-cli-contract` job is still open.

## M1-E2-T1 reviews — ADR-002 (agent-native tool governance): SEC and REV, round 1

Workflow `wf_f2e7baa5-28e`: two independent read-only reviews of `docs/engineering/adr/ADR-agent-native-tool-governance.md`, checked against the code and against AG-02, AG-04 and AG-05 as implemented on `integrate/wave-2b`. Both verdicts are **request_changes**. The full findings are kept for the revision.

| Done-when item | SEC | REV |
|---|---|---|
| A matrix row per provider mode (each Claude permission mode, each Codex sandbox/approval pair, each Gemini approval mode), with the selecting Koda policy state and the argv | not met: rows are per built-in level; acceptEdits, auto, manual, the other Codex approval policies and Gemini plan are missing | not met |
| Schema of the per-agent opt-in field and its audit event | not met: the field is defined, but no audit event schema | not met |
| Text of the operator migration notice | not met: only a banner and a button label | not met |
| Test plan naming each M1-E2-T2 argv test and each D-011 and D-012 test | not met: categories only | not met |
| SEC and REV approving reviews recorded | not met | not met |

Findings shared by both lenses:

- **critical:** D-011 (how policy-approved `<agent_cmd>` shell, git and supervised writes are authorised) and D-012 (pending approvals across processes) are not designed, although M1-E2-T1 requires both and M3-E3-T1 and M3-E3-T2 depend on them.
- **major:** every Codex level depends on L2 confinement alone. Under `RUNTIME_CONFINEMENT=off`, read_only, dry runs, child runs and the squad planner run `danger-full-access`, which is weaker than today's dry-run `--sandbox read-only`.

Other SEC findings:

- **majors:**
  - a provider switch at the same level is not gated;
  - internal `publish_agent` callers bypass `confirm_escalation`;
  - model-written instruction files persist across turns, `--restricted` does not stop them, and the provider-home rewrite misses `AGENTS.md` and `GEMINI.md`;
  - the OAuth sync-back moves files from model-writable homes into the login home that the key-holding `app` container reads;
  - at read_only, the CLIs' own read tools reach the credential;
  - signed snapshots can be rolled back or replayed.
- **minors:**
  - Landlock network claims are overstated;
  - Gemini's tool exclusion is a denylist that fails open;
  - the spawn audit has blind spots;
  - the text has drifted from AG-02, AG-04 and AG-05;
  - the plan contradicts the ADR on key handling.
- **nit:** the Gemini stdin channel lets user text forge a system block.

Other REV findings:

- **majors:**
  - AG-06 contradicts ADR-008 step 1 (resolved by ADR-039, which folds M1-E4-T9 into AG-06);
  - no mapping for the replaced plan items M1-E2-T2..T4;
  - the critical path runs through dependencies the highest-value fixes do not need;
  - Codex resume is unproven and AG-24 does not depend on the replay task.
- **minors:**
  - stale Gemini argv and a wrong `none` row;
  - the `*_BIN` change from command line to one executable path is not recorded as a breaking change;
  - the claim that probes and argv cannot drift is overstated;
  - AG-05 operator behaviour and the AG-04 startup window are missing;
  - AG-18 adds a second approval path;
  - an untestable grep guard;
  - three overlapping read-only reports;
  - AG-16 deletes M1-E4-T7's backend.

Outcome: M1-E2-T1 stays `in-review`. The ADR gets a revision (round 2), and both lenses review it again.
