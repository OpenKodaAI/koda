# Validation Report

Evidence log for completed tasks. Each entry lists the exact commands run and
their observed results. Environment notes: local PostgreSQL 16 + pgvector;
runs that share the machine with audit agents use a dedicated database and a
dedicated `SECURITY_GRPC_TARGET` port, because the test session attaches to any
security-guard service already listening on the default port 50065.

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
