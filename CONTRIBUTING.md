# Contributing To Koda

Thank you for helping improve Koda.

This guide covers the default contribution workflow for product code, documentation, and platform-facing changes.

## Development Setup

```bash
pip install -e ".[dev]"
pnpm install
ruff check .
ruff format --check .
mypy koda/ --ignore-missing-imports
pytest --cov=koda --cov-report=term-missing
pnpm lint:web
pnpm test:web
pnpm build:web
```

Koda needs `cryptography` 50.0.2 or later for security fixes. Its wheels cover
Apple silicon macOS, x86-64 Windows and Linux on x86-64, ARM64, ARMv7 and
ppc64le, which includes the Docker images. Elsewhere, including Intel (x86_64)
macOS, 32-bit Windows and Windows on ARM with an ARM64 Python, the install
builds it from source. That needs Rust, OpenSSL and a C compiler: on macOS, the
Xcode command line tools (`xcode-select --install`) and
`brew install openssl@3 rust`; on Windows, the Microsoft C++ Build Tools, Rust
from rustup and an OpenSSL build that `OPENSSL_DIR` points to. See
[cryptography's installation guide](https://cryptography.io/en/latest/installation/).

For product-facing local work, prefer the Docker-first stack documented in:

- [README.md](README.md)
- [docs/install/local.md](docs/install/local.md)

## Validation Matrix

Run the standard validation commands before opening a pull request:

- `ruff check .`
- `ruff format --check .`
- `mypy koda/ --ignore-missing-imports`
- `pytest --cov=koda --cov-report=term-missing`
- `pnpm lint:web`
- `pnpm test:web`
- `pnpm build:web`
- `pytest -q tests/test_open_source_hygiene.py tests/test_public_docs.py tests/test_installation_assets.py`

If your change touches the Rust workspace, also run:

- `cargo fmt --manifest-path rust/Cargo.toml --all --check`
- `cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml --workspace`

The cross-language tests in `tests/integration` run `cargo build --release -p <crate>` once per
session, even when a binary already exists (the build is incremental, so an up-to-date crate
takes seconds), and run the executable that build reports, never an older one. When `cargo` is
missing or the build fails, those tests are skipped locally and fail under `CI`. In a checkout
with no earlier release build, the first run compiles the crate and its dependencies from
scratch (for `koda-bot-gateway`, about 530 MB of release output and a few minutes on 4 CPUs).
Copying or hard-linking a prebuilt binary into `rust/target/release` does not avoid that build:
cargo has no record of it, so it rebuilds and replaces the file. A `CARGO_TARGET_DIR` set in the
environment is honoured, but do not share one target directory between checkouts that run these
tests at the same time: every build writes the same `release/<crate>` path, so another
checkout's build can replace the binary after this session built it and before a test runs it.
Keep one target directory per checkout; the download cache in `CARGO_HOME` is already shared.

`pytest` starts its own Rust security guard (through `cargo run`) on a private Unix socket for
each session, so concurrent runs on one host do not interfere and an ambient
`SECURITY_GRPC_TARGET` is ignored. Without `cargo` every test is skipped with a banner (and the
run fails under `CI`). To reuse one already-running guard across several checkouts, start
`rust/target/debug/koda-security-service` with `SECURITY_GRPC_TARGET=127.0.0.1:<port>` and set
`KODA_TEST_SECURITY_GUARD_TARGET=127.0.0.1:<port>` for each run; the run fails if that guard is
unreachable. A shared guard runs whatever build it was started from, so do not share one when
validating changes to `rust/koda-security-*`. `KODA_SECURITY_GUARD_STARTUP_TIMEOUT` (seconds)
raises the startup wait for cold builds.

The session's guard, the Rust binaries the integration tests start and the nginx of the proxy
smoke test each run under a small watchdog (`tests/_owned_process.py`). It checks ten times a
second whether the pytest process is gone and then stops them, even when pytest was killed before
its teardown could run. Start any new long-lived test process with `spawn_owned` and stop it with
`stop_owned`, not with a bare `subprocess.Popen`.

Each test also gets its own empty `HOME` (with `CLAUDE_CONFIG_DIR` and `CODEX_HOME` unset), so a
test never reads or deletes your files. Provider disconnect tests remove CLI login files under
`~/.claude`, `~/.codex` and `~/.gemini`. Write tests against `os.environ["HOME"]`, never against
your real home directory.

Tests marked `postgres` run only when `POSTGRES_TEST_DSN` points at a database (`pytest -m
postgres`); otherwise they are skipped. They share one schema in that database and empty tables
with `TRUNCATE` between tests, so the Postgres suite is serial-only: do not run it with parallel
workers, and give each concurrent session its own database. Squad tests reset their tables with
`reset_squad_runtime_tables` from `tests/postgres_fixtures.py` instead of truncating them directly.
Fixtures that reset Koda's shared Postgres backends call `close_shared_postgres_backends` from the
same module, which closes their connection pools; clearing the cache directly leaves those
connections open until the server refuses new clients.

The end-to-end agent-turn tests in `tests/test_services/test_agent_turn_e2e.py` run real turns
through the queue worker and replace only the provider adapter (`tests/fakes/provider.py`) and
Telegram (`tests/fakes/telegram.py`). Reuse those fakes for new end-to-end tests instead of
patching the orchestration path.

To run the same local gate from one command:

```bash
scripts/check_pr_quality.sh
```

You can also opt into the repository pre-push hook:

```bash
git config core.hooksPath scripts/git-hooks
```

The hook runs the full PR-quality gate before `git push`. It is optional because the suite is intentionally broad.

## GitHub CI

GitHub Actions now uses two primary workflows:

- `pr-quality` for required pull-request checks on `main`
- `security` for dependency audits, SAST, CodeQL, and container scanning on pull requests, `main`, and a weekly schedule

The required PR check names are:

- `pr-quality / python-quality`
- `pr-quality / python-tests-3.11`
- `pr-quality / python-tests-3.12`
- `pr-quality / web-quality`
- `pr-quality / repo-hygiene`
- `pr-quality / rust-quality`
- `pr-quality / docker-smoke`
- `security / dependency-audit`
- `security / sast`
- `security / container-scan`

The `security` workflow also publishes SARIF findings for CodeQL, Gitleaks, and Trivy into the GitHub Security tab when permissions allow it, and uploads CI artifacts for `pytest`, coverage XML, `vitest`, and container scan reports.

When a CI failure happens:

- read `pytest.xml` and `coverage.xml` artifacts for Python regressions
- read the `vitest.junit.xml` artifact for web test failures
- read the uploaded SARIF or Security tab findings for dependency, secret, static-analysis, or container issues
- run `python3 scripts/check_master_plan.py` when `repo-hygiene` reports a status, evidence or dependency problem in `docs/engineering/MASTER_PLAN.md`; it names the line and the rule it breaks
- read the `docker-smoke` artifact logs when the stack fails to boot in CI

## Pull Request Expectations

- keep changes scoped and reviewable
- include tests when behavior changes
- update public docs when installation, APIs, or operator workflows change
- add a `CHANGELOG.md` entry under `## [Unreleased]` for a change users, operators or API clients can notice (see [docs/reference/releases.md](docs/reference/releases.md#changelog))
- update repository guidance when architecture or contributor-facing workflows change
- do not commit local runtime state, caches, secrets, or machine-specific paths

## Documentation Policy

Koda maintains a single documentation tree at `docs/` for public product, operator, and contributor documentation. The application code is split between:

- the Python platform at the repository root
- the web dashboard in `apps/web`

When public behavior changes, update the relevant file under `docs/`.
When operational rules for coding agents change, update `CLAUDE.md`.

## Naming And Branding Rules

- product-facing branding is `Koda`
- product-facing domain language uses `agent`, not legacy `bot`
- examples must stay generic and open-source friendly
- public docs must not include personal identifiers, local machine paths, or customer-specific naming

## Review Checklist

Before submitting:

- confirm tests and validation passed
- confirm new links resolve correctly
- confirm screenshots or assets reflect real current product surfaces
- confirm there is no private or local-only data in the diff
