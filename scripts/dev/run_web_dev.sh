#!/bin/sh
set -eu

ROOT_DIR="${KODA_DEV_ROOT:-/workspace}"
STAMP_FILE="${KODA_DEV_STAMP_FILE:-${ROOT_DIR}/node_modules/.koda-dev-pnpm-deps.sha1}"
CACHE_DIR="${KODA_DEV_WEB_CACHE_DIR:-/opt/koda-dev-web}"
CACHE_HASH_FILE="${CACHE_DIR}/pnpm-deps.sha1"
PNPM_STORE_DIR="${KODA_DEV_PNPM_STORE_DIR:-/root/.local/share/pnpm/store}"

mkdir -p "$(dirname "${STAMP_FILE}")"
mkdir -p "${PNPM_STORE_DIR}"

cd "${ROOT_DIR}"

export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
export npm_config_store_dir="${PNPM_STORE_DIR}"
corepack enable >/dev/null 2>&1 || true

CURRENT_HASH="$(cat package.json pnpm-lock.yaml apps/web/package.json | sha1sum | awk '{print $1}')"
PREVIOUS_HASH=""

if [ -f "${STAMP_FILE}" ]; then
  PREVIOUS_HASH="$(cat "${STAMP_FILE}")"
fi

if [ ! -f "${ROOT_DIR}/node_modules/.modules.yaml" ] && [ -f "${CACHE_HASH_FILE}" ] && [ "$(cat "${CACHE_HASH_FILE}")" = "${CURRENT_HASH}" ]; then
  mkdir -p "${ROOT_DIR}/node_modules" "${ROOT_DIR}/apps/web/node_modules"
  cp -a "${CACHE_DIR}/node_modules-root/." "${ROOT_DIR}/node_modules/"
  cp -a "${CACHE_DIR}/node_modules-app/." "${ROOT_DIR}/apps/web/node_modules/"
  if [ -d "${CACHE_DIR}/pnpm-store" ]; then
    cp -a "${CACHE_DIR}/pnpm-store/." "${PNPM_STORE_DIR}/"
  fi
  printf '%s' "${CURRENT_HASH}" > "${STAMP_FILE}"
  PREVIOUS_HASH="${CURRENT_HASH}"
fi

if [ "${CURRENT_HASH}" != "${PREVIOUS_HASH}" ] || [ ! -f "${ROOT_DIR}/node_modules/.modules.yaml" ] || [ ! -d "${ROOT_DIR}/apps/web/node_modules/.bin" ]; then
  CI=true pnpm install --frozen-lockfile --store-dir "${PNPM_STORE_DIR}"
  printf '%s' "${CURRENT_HASH}" > "${STAMP_FILE}"
fi

cd apps/web
mkdir -p .next
exec pnpm dev
