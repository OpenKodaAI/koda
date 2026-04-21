#!/usr/bin/env bash

set -euo pipefail

ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/docker}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-90}"
WAIT_SLEEP_SECONDS="${WAIT_SLEEP_SECONDS:-2}"
COMPOSE_ARGS=()

if [ -n "${COMPOSE_FILE:-}" ]; then
  COMPOSE_ARGS+=(-f "${COMPOSE_FILE}")
fi

compose() {
  if [ "${#COMPOSE_ARGS[@]}" -gt 0 ]; then
    docker compose "${COMPOSE_ARGS[@]}" "$@"
  else
    docker compose "$@"
  fi
}

probe_url() {
  local url="$1"
  curl -fsSL \
    --retry 5 \
    --retry-delay 2 \
    --retry-connrefused \
    --retry-all-errors \
    --max-time 15 \
    "$url" >/dev/null
}

capture_diagnostics() {
  mkdir -p "${ARTIFACT_DIR}"

  {
    echo "# docker compose ps"
    compose ps
  } > "${ARTIFACT_DIR}/compose-ps.txt" 2>&1 || true

  {
    echo "# docker compose images"
    compose images
  } > "${ARTIFACT_DIR}/compose-images.txt" 2>&1 || true

  compose logs --no-color > "${ARTIFACT_DIR}/compose.log" 2>&1 || true

  local container_ids
  container_ids="$(compose ps -q 2>/dev/null || true)"
  if [ -n "${container_ids}" ]; then
    docker inspect ${container_ids} > "${ARTIFACT_DIR}/docker-inspect.json" 2>&1 || true
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"

  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
    if probe_url "${url}"; then
      echo "[docker-smoke] ${name} ready at ${url}"
      return 0
    fi

    if (( attempt % 10 == 0 )); then
      echo "[docker-smoke] waiting for ${name} (${attempt}/${WAIT_ATTEMPTS})"
      compose ps || true
    fi

    sleep "${WAIT_SLEEP_SECONDS}"
  done

  echo "[docker-smoke] timed out waiting for ${name} at ${url}" >&2
  return 1
}

main() {
  trap 'status=$?; if [ "${status}" -ne 0 ]; then capture_diagnostics; fi; exit "${status}"' EXIT

  rm -rf "${ARTIFACT_DIR}"
  cp .env.example .env
  compose config -q
  compose up -d --build

  wait_for_url "control-plane health" "http://127.0.0.1:8090/health"
  wait_for_url "web health" "http://127.0.0.1:3000/api/health"
  wait_for_url "dashboard root" "http://127.0.0.1:3000/"
  wait_for_url "dashboard setup" "http://127.0.0.1:3000/control-plane/setup"
  wait_for_url "control-plane shell" "http://127.0.0.1:3000/control-plane"
  wait_for_url "control-plane openapi" "http://127.0.0.1:8090/openapi/control-plane.json"

  # Run a second pass once the stack is warm to catch transient restarts.
  probe_url "http://127.0.0.1:8090/health"
  probe_url "http://127.0.0.1:3000/api/health"
  probe_url "http://127.0.0.1:3000/"
  probe_url "http://127.0.0.1:3000/control-plane/setup"
  probe_url "http://127.0.0.1:3000/control-plane"
  probe_url "http://127.0.0.1:8090/openapi/control-plane.json"

  echo "[docker-smoke] stack passed endpoint verification"
}

main "$@"
