#!/usr/bin/env bash

set -euo pipefail

ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/docker}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-90}"
WAIT_SLEEP_SECONDS="${WAIT_SLEEP_SECONDS:-2}"
# The bundled reverse proxy runs in a pinned nginx on the host network, in front
# of the ports the stack publishes on loopback, as on an operator's host.
PROXY_TEMPLATE="packages/cli/release/bundle/proxy/nginx.conf"
PROXY_IMAGE="${PROXY_IMAGE:-nginx:1.30.6-alpine@sha256:901e593c95dc85f5a729f5765516321366ef4ac401821431d408897e95287d0a}"
PROXY_PORT="${PROXY_PORT:-18080}"
PROXY_CONTAINER="${PROXY_CONTAINER:-koda-docker-smoke-proxy}"
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
    --connect-timeout 2 \
    --max-time 5 \
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

  docker logs "${PROXY_CONTAINER}" > "${ARTIFACT_DIR}/proxy.log" 2>&1 || true
}

stop_bundled_proxy() {
  docker rm -f "${PROXY_CONTAINER}" >/dev/null 2>&1 || true
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

# The API believes X-Forwarded-For from the dashboard only when the address the
# dashboard connects from is one that `web` resolves to inside `app`. Both
# containers sit on two networks, so check that the two agree; if they did not,
# every browser would silently share one rate-limit bucket.
verify_dashboard_is_trusted_by_api() {
  local source resolved
  source="$(compose exec -T web node -e '
    const socket = require("node:net").connect(8090, "app", () => {
      console.log(socket.localAddress.replace(/^::ffff:/, ""));
      socket.end();
    });
    socket.on("error", () => process.exit(1));
  ')"
  resolved="$(compose exec -T app python -c '
import socket
print(" ".join(sorted({info[4][0] for info in socket.getaddrinfo("web", None)})))
')"
  case " ${resolved} " in
    *" ${source} "*)
      echo "[docker-smoke] API trusts the dashboard's address ${source}"
      ;;
    *)
      echo "[docker-smoke] dashboard connects from ${source:-?} but app resolves web to ${resolved:-nothing}" >&2
      return 1
      ;;
  esac
}

# Load the bundled proxy/nginx.conf into a real nginx and prove through it that
# browser sign-in, the runtime relay WebSocket and API-token calls reach the
# right upstream (scripts/proxy_smoke.py lists the checks).
verify_bundled_proxy() {
  local config bootstrap_code
  mkdir -p "${ARTIFACT_DIR}"
  config="$(cd "${ARTIFACT_DIR}" && pwd)/proxy-nginx.conf"
  python3 scripts/proxy_smoke.py render --listen "127.0.0.1:${PROXY_PORT}" "${PROXY_TEMPLATE}" > "${config}"

  stop_bundled_proxy
  # conf.d/default.conf is included in the image's http context, like
  # /etc/nginx/conf.d/koda.conf on a host; replacing it drops the stock site.
  docker run --rm --network host \
    -v "${config}:/etc/nginx/conf.d/default.conf:ro" \
    "${PROXY_IMAGE}" nginx -t
  docker run -d --name "${PROXY_CONTAINER}" --network host \
    -v "${config}:/etc/nginx/conf.d/default.conf:ro" \
    "${PROXY_IMAGE}" >/dev/null
  wait_for_url "bundled proxy" "http://127.0.0.1:${PROXY_PORT}/api/health"

  # The control plane writes the first-boot setup code when its auth status is
  # first read; read it from the file, as an operator does over SSH.
  probe_url "http://127.0.0.1:8090/api/control-plane/auth/status"
  bootstrap_code="$(compose exec -T app sh -c 'head -n 1 "${STATE_ROOT_DIR:-/var/lib/koda/state}/control_plane/bootstrap.txt"')"
  if [ -z "${bootstrap_code}" ]; then
    echo "[docker-smoke] no first-boot setup code; the proxy smoke needs a fresh stack" >&2
    return 1
  fi

  KODA_PROXY_SMOKE_BOOTSTRAP_CODE="${bootstrap_code}" python3 scripts/proxy_smoke.py check \
    --proxy-url "http://127.0.0.1:${PROXY_PORT}" --env-file .env
}

main() {
  trap 'status=$?; if [ "${status}" -ne 0 ]; then capture_diagnostics; fi; stop_bundled_proxy; exit "${status}"' EXIT

  rm -rf "${ARTIFACT_DIR}"
  cp .env.example .env
  python3 scripts/generate_env_secrets.py
  compose config -q
  compose up -d --build

  wait_for_url "control-plane health" "http://127.0.0.1:8090/health"
  wait_for_url "web health" "http://127.0.0.1:3000/api/health"
  wait_for_url "dashboard root" "http://127.0.0.1:3000/"
  wait_for_url "dashboard setup" "http://127.0.0.1:3000/setup"
  wait_for_url "control-plane shell" "http://127.0.0.1:3000/control-plane"
  wait_for_url "control-plane openapi" "http://127.0.0.1:8090/openapi/control-plane.json"

  # Run a second pass once the stack is warm to catch transient restarts.
  probe_url "http://127.0.0.1:8090/health"
  probe_url "http://127.0.0.1:3000/api/health"
  probe_url "http://127.0.0.1:3000/"
  probe_url "http://127.0.0.1:3000/setup"
  probe_url "http://127.0.0.1:3000/control-plane"
  probe_url "http://127.0.0.1:8090/openapi/control-plane.json"
  verify_dashboard_is_trusted_by_api
  verify_bundled_proxy

  echo "[docker-smoke] stack passed endpoint verification"
}

main "$@"
