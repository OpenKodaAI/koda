#!/usr/bin/env bash
# Idempotent restart for the local-native koda stack.
#
# Why this exists (P1-2 of docs/architecture/production-deployment-roadmap.md):
# ``dev-up.sh`` keys off PID files under ``~/.koda-local/var/run/``. When a
# previous run was killed hard (Ctrl-C inside a hung supervisor, ``kill -9``,
# OOM, etc.) those files survive but the listed processes are dead. The next
# ``dev-up.sh`` then assumes the service is healthy and refuses to start it,
# leaving the stack half-up. MinIO additionally writes a data-directory
# lock that survives process death, producing
# ``Another instance is already running`` on the next start.
#
# This script handles both cases: it runs ``dev-down.sh`` to release whatever
# the previous boot left behind, then re-runs ``dev-up.sh``. Use it any time
# you want a clean restart without thinking about which PID files are stale.

set -euo pipefail

KODA_LOCAL="${KODA_LOCAL:-${HOME}/.koda-local}"
SCRIPTS_DIR="${KODA_LOCAL}/scripts"

if [[ ! -d "${SCRIPTS_DIR}" ]]; then
  echo "error: ${SCRIPTS_DIR} not found — install local-native koda first." >&2
  exit 2
fi

DOWN="${SCRIPTS_DIR}/dev-down.sh"
UP="${SCRIPTS_DIR}/dev-up.sh"

for path in "${DOWN}" "${UP}"; do
  if [[ ! -x "${path}" ]]; then
    echo "error: ${path} is missing or not executable." >&2
    exit 2
  fi
done

echo "[koda] dev-restart: stopping..."
"${DOWN}" || true

# Drop any PID files the previous run may have left behind. ``dev-down.sh``
# does this for the services it knows about, but a partial boot may have
# created files for services it never saw stop, so we sweep them
# defensively.
rm -f "${KODA_LOCAL}/var/run/"*.pid 2>/dev/null || true

echo "[koda] dev-restart: starting..."
exec "${UP}"
