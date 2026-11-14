# Quality Baseline

Verified baseline captured before any code change, on commit `4bed7bd`
(branch `claude/dreamy-cerf-mhvbwn`), 2026-11-14, in the `koda` cloud
environment (4 CPUs, no Docker, no provider keys).

Every row below was executed; logs were inspected, not assumed.
Environment: `AGENT_TOKEN=test-token`, `ALLOWED_USER_IDS=123456789` (CI dummy values).

## Required validation gates (CLAUDE.md)

| Gate | Command | Result | Time | Notes |
|---|---|---|---|---|
| Python lint | `ruff check .` | pass | 6s | — |
| Python format | `ruff format --check .` | pass | <1s | 703 files |
| Python types | `mypy koda/ --ignore-missing-imports` | pass | 5s | 358 files; pyproject has 13 unused `[[tool.mypy.overrides]]` module sections |
| Python tests | `pytest --cov=koda --cov-report=term-missing` | pass | 93s | 4874 passed, 200 skipped, 9 warnings; line coverage 61% |
| Web lint | `pnpm lint:web` | pass | 39s | 0 errors, 40 warnings (30 `react-hooks/exhaustive-deps`, 10 `no-unused-vars`) |
| Web tests | `pnpm test:web` | pass | 201s | 154 files, 686 tests |
| Web build | `pnpm build:web` | pass | 44s | needs `fonts.googleapis.com` / `fonts.gstatic.com` |
| Rust format | `cargo fmt --check --manifest-path rust/Cargo.toml` | **fails (tooling)** | — | rustfmt 1.9 prints "Failed to find targets" for a virtual workspace manifest when run from the repo root. `cargo fmt --all --check --manifest-path rust/Cargo.toml` and `cd rust && cargo fmt --check` both pass. CI runs it inside `rust/`, so only the documented command is wrong. |
| Rust lint | `cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings` | pass | 2s (cached) | — |
| Rust tests | `cargo test --manifest-path rust/Cargo.toml --workspace` | pass | 44s | — |

## Skipped tests (not counted as passing)

- 188 tests marked `postgres` skip without `POSTGRES_TEST_DSN` (no Docker for testcontainers).
- Running them against a local PostgreSQL 16 + pgvector (pre-baseline probe): 96 passed, 43 failed, 47 errors.
  - 47 errors: test fixture `TRUNCATE`s `squad_threads` / `squad_messages` without `CASCADE` while `squad_reply_obligations` references them.
  - 19 failures: `KNOWLEDGE_V2_POSTGRES_DSN` not set by the fixture when `POSTGRES_TEST_DSN` is used (only the testcontainers path sets it).
  - Remaining failures not yet triaged.
- Consequence at baseline time: the production persistence path (Postgres) was untested everywhere, CI included (no DSN, no `testcontainers` dependency).
- Resolved by M0-PG-FIXTURES (see `VALIDATION_REPORT.md`): 186 passed, 2 skipped with a DSN; new `python-postgres-tests` CI job.

## Python line coverage by package

| Package | Statements | Missed | Coverage |
|---|---:|---:|---:|
| dashboard | 59 | 59 | 0% |
| runtime | 70 | 70 | 0% |
| channels | 1640 | 1011 | 38% |
| state | 2732 | 1624 | 41% |
| agents | 633 | 338 | 47% |
| control_plane | 13876 | 6468 | 53% |
| memory | 2591 | 1220 | 53% |
| knowledge | 2494 | 1103 | 56% |
| squads | 4228 | 1717 | 59% |
| services | 29502 | 10353 | 65% |
| handlers | 4090 | 1177 | 71% |
| utils | 3317 | 829 | 75% |
| internal_rpc | 1599 | 374 | 77% |
| skills | 1337 | 196 | 85% |
| **Total** | **73779** | **28921** | **61%** |

Modules at 0% include the non-Telegram channel adapters (Discord, Instagram,
Messenger, WhatsApp, Teams), `memory/manager.py`, the memory/knowledge
schedulers, `services/semantic_cache_index.py` and `dashboard/aggregator.py`.
Low coverage on `state` and `control_plane` is partly the skipped Postgres suite.

## Not yet measured

- End-to-end browser journeys (no Playwright suite exists in the repo; runtime smoke agent in progress).
- Startup of the full stack (runtime smoke agent in progress).
- Dependency vulnerability scan (`pip-audit` / `pnpm audit` / `cargo audit`), blocked or pending network access.
- Performance baselines.

## Raw evidence

Logs from this run were kept in the session scratchpad (`baseline/*.log`); the
numbers above are copied from them verbatim.
