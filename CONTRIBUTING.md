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
python3 scripts/generate_repo_map.py --check
```

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
- `pytest -q tests/test_ai_docs.py tests/test_repo_map.py tests/test_open_source_hygiene.py`

If your change touches the repository guidance layer, also run:

- `python3 scripts/generate_repo_map.py --check`
- `pytest -q tests/test_ai_docs.py tests/test_repo_map.py tests/test_open_source_hygiene.py`

If your change touches the Rust workspace, also run:

- `cargo fmt --check --manifest-path rust/Cargo.toml`
- `cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings`
- `cargo test --manifest-path rust/Cargo.toml --workspace`

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
- read the `docker-smoke` artifact logs when the stack fails to boot in CI

## Pull Request Expectations

- keep changes scoped and reviewable
- include tests when behavior changes
- update public docs when installation, APIs, or operator workflows change
- update repository guidance when architecture or contributor-facing workflows change
- do not commit local runtime state, caches, secrets, or machine-specific paths

## Documentation Policy

Koda maintains two documentation layers:

- `docs/` for public product, operator, and contributor documentation
- `docs/ai/` for repository guidance aimed at LLM tooling and code assistants

The application code is split between:

- the Python platform at the repository root
- the web dashboard in `apps/web`

When public behavior changes, update the relevant file under `docs/`.
When repository guidance changes, keep `AGENTS.md`, `CLAUDE.md`, `docs/ai/*`, and the generated repo map aligned.

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
