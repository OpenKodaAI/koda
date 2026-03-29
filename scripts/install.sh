#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
DOCKER_BIN=(docker)

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

ensure_docker() {
  if command_exists docker && docker compose version >/dev/null 2>&1; then
    return
  fi

  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "Docker Compose is required. On non-Linux systems, install Docker Desktop first." >&2
    exit 1
  fi

  if ! command_exists apt-get; then
    echo "Automatic Docker installation is supported only on apt-based Linux hosts." >&2
    exit 1
  fi

  if ! command_exists sudo; then
    echo "sudo is required to install Docker automatically." >&2
    exit 1
  fi

  echo "Installing Docker and Docker Compose..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    ${VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

resolve_docker_bin() {
  if docker info >/dev/null 2>&1; then
    DOCKER_BIN=(docker)
    return
  fi
  if command_exists sudo && sudo docker info >/dev/null 2>&1; then
    DOCKER_BIN=(sudo docker)
    return
  fi
  echo "Docker is installed but the current user cannot access it." >&2
  exit 1
}

write_env_if_missing() {
  if [[ -f "${ENV_FILE}" ]]; then
    echo ".env already exists; preserving current values."
    return
  fi

  python3 - <<'PY' > "${ENV_FILE}"
import secrets
import string

control_plane_token = secrets.token_urlsafe(32)
runtime_token = secrets.token_urlsafe(32)
master_key = secrets.token_urlsafe(48)
postgres_password = secrets.token_urlsafe(24)
s3_access_key = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20))
s3_secret = secrets.token_urlsafe(24)

print(
    "\n".join(
        [
            "CONTROL_PLANE_ENABLED=true",
            "CONTROL_PLANE_BIND=0.0.0.0",
            "CONTROL_PLANE_PORT=8090",
            "WEB_PORT=3000",
            f"CONTROL_PLANE_API_TOKEN={control_plane_token}",
            f"RUNTIME_LOCAL_UI_TOKEN={runtime_token}",
            f"CONTROL_PLANE_MASTER_KEY={master_key}",
            "STATE_BACKEND=postgres",
            "OBJECT_STORAGE_REQUIRED=true",
            "STATE_ROOT_DIR=/var/lib/koda/state",
            "RUNTIME_EPHEMERAL_ROOT=/var/lib/koda/runtime",
            "ARTIFACT_STORE_DIR=/var/lib/koda/artifacts",
            "KNOWLEDGE_V2_STORAGE_MODE=primary",
            f"QUICKSTART_POSTGRES_PASSWORD={postgres_password}",
            "QUICKSTART_POSTGRES_DB=koda",
            "QUICKSTART_POSTGRES_USER=koda",
            f"KNOWLEDGE_V2_POSTGRES_DSN=postgresql://koda:{postgres_password}@postgres:5432/koda",
            "KNOWLEDGE_V2_POSTGRES_SCHEMA=knowledge_v2",
            "KNOWLEDGE_V2_S3_BUCKET=koda-objects",
            "KNOWLEDGE_V2_S3_PREFIX=koda",
            "KNOWLEDGE_V2_S3_ENDPOINT_URL=http://seaweedfs:8333",
            "KNOWLEDGE_V2_S3_REGION=us-east-1",
            f"KNOWLEDGE_V2_S3_ACCESS_KEY_ID={s3_access_key}",
            f"KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY={s3_secret}",
        ]
    )
)
PY

  echo "Created .env with generated quickstart credentials."
}

show_next_steps() {
  local port web_port token host
  port="$(grep -E '^CONTROL_PLANE_PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
  web_port="$(grep -E '^WEB_PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
  token="$(grep -E '^CONTROL_PLANE_API_TOKEN=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
  host="$(hostname -I 2>/dev/null | awk '{print $1}')"
  host="${host:-127.0.0.1}"
  echo
  echo "Koda platform stack is up."
  echo "Dashboard URL:"
  echo "  http://${host}:${web_port:-3000}"
  echo
  echo "Bootstrap URL:"
  echo "  http://${host}:${port:-8090}/setup?token=${token}"
  echo
  echo "If you are on the same machine, localhost also works:"
  echo "  Dashboard: http://127.0.0.1:${web_port:-3000}"
  echo "  Bootstrap: http://127.0.0.1:${port:-8090}/setup?token=${token}"
  echo
  echo "No provider or agent env vars are required for bootstrap; configure them in the web UI."
}

wait_for_http_service() {
  local url label
  url="$1"
  label="$2"
  for _ in $(seq 1 60); do
    if python3 - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("${url}", timeout=2)
PY
    then
      return
    fi
    sleep 2
  done
  echo "Timed out waiting for ${label} at ${url}." >&2
  exit 1
}

main() {
  ensure_docker
  resolve_docker_bin
  write_env_if_missing
  cd "${ROOT_DIR}"
  "${DOCKER_BIN[@]}" compose up -d --build
  wait_for_http_service \
    "http://127.0.0.1:$(grep -E '^CONTROL_PLANE_PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || echo 8090)/health" \
    "the control plane"
  wait_for_http_service \
    "http://127.0.0.1:$(grep -E '^WEB_PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || echo 3000)" \
    "the web dashboard"
  python3 scripts/doctor.py \
    --env-file "${ENV_FILE}" \
    --base-url "http://127.0.0.1:$(grep -E '^CONTROL_PLANE_PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || echo 8090)" \
    --dashboard-url "http://127.0.0.1:$(grep -E '^WEB_PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || echo 3000)"
  show_next_steps
}

main "$@"
