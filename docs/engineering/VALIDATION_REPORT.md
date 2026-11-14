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
