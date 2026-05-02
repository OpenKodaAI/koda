#!/usr/bin/env bash
# Build + install the koda-command-guard PyO3 wheel into the active venv.
#
# Why this exists (Phase 1A of docs/architecture/production-deployment-roadmap.md):
# the Rust DFA matcher is built outside the cargo workspace so it doesn't
# break ``cargo test --workspace`` (which has no Python interpreter wired
# in). Production deploys pre-build the wheel; developers run this script
# once after cloning to get the fast path locally. Without the wheel, the
# Python fallback in ``koda/services/command_guard.py`` keeps everything
# working — just slower on the hot path.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CRATE_DIR="${REPO_ROOT}/rust/koda-command-guard"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "error: ${VENV_DIR} not found. Activate or create the venv first." >&2
  exit 2
fi

PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
MATURIN="${VENV_DIR}/bin/maturin"

if [[ ! -x "${MATURIN}" ]]; then
  echo "[koda] installing maturin into ${VENV_DIR}..."
  "${PIP}" install -q "maturin>=1.7,<2.0"
fi

echo "[koda] building koda-command-guard wheel..."
(cd "${CRATE_DIR}" && "${MATURIN}" build --release --interpreter "${PYTHON}")

WHEEL_DIR="${CRATE_DIR}/target/wheels"
WHEEL_PATH="$(ls -1t "${WHEEL_DIR}"/koda_command_guard-*.whl | head -n 1)"

if [[ -z "${WHEEL_PATH}" ]]; then
  echo "error: maturin reported success but no wheel found under ${WHEEL_DIR}." >&2
  exit 1
fi

echo "[koda] installing ${WHEEL_PATH##*/} into venv..."
"${PIP}" install --quiet --force-reinstall "${WHEEL_PATH}"

echo "[koda] verifying import..."
"${PYTHON}" -c "import koda_command_guard; print('koda_command_guard', koda_command_guard.__version__)"
