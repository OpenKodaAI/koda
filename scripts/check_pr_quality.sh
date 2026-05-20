#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

run uv sync --locked
run uv run ruff check .
run uv run ruff format --check .
run uv run mypy koda/ --ignore-missing-imports
run uv run pytest --cov=koda --cov-report=term-missing

run pnpm install --frozen-lockfile
run pnpm audit --audit-level=moderate
run pnpm lint:web
run pnpm test:web
run pnpm build:web

run uv run python3 scripts/sync_npm_readme.py
run uv run pytest -q tests/test_open_source_hygiene.py tests/test_public_docs.py tests/test_installation_assets.py

run cargo fmt --manifest-path rust/Cargo.toml --all --check
run cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings
run cargo test --manifest-path rust/Cargo.toml --workspace

mkdir -p artifacts/security/snyk
run uv export \
  --format requirements.txt \
  --locked \
  --all-groups \
  --all-extras \
  --no-editable \
  --no-emit-project \
  --no-emit-workspace \
  --no-hashes \
  --no-header \
  --no-annotate \
  --output-file artifacts/security/snyk/python-requirements.txt

if [[ -n "${SNYK_TOKEN:-}" && -x "$(command -v snyk || true)" ]]; then
  run snyk test \
    --all-projects \
    --detection-depth=5 \
    --exclude=.git,.koda-release,.next,.mypy_cache,.pnpm-store,.pytest_cache,.ruff_cache,.venv,venv,artifacts,build,coverage,dist,downloads,node_modules,output,target,release \
    --severity-threshold=high
  run snyk test \
    --file=artifacts/security/snyk/python-requirements.txt \
    --package-manager=pip \
    --severity-threshold=high
else
  printf '\n==> skipping Snyk scan (set SNYK_TOKEN and install snyk to enable it locally)\n'
fi
