#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_PACKAGE_DIR="${ROOT_DIR}/packages/cli"
PRODUCT_DIR="${ROOT_DIR}/.koda-release"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

ensure_apt_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "Automatic dependency installation is supported only on apt-based Linux hosts." >&2
    exit 1
  fi

  if ! command_exists apt-get; then
    echo "Automatic dependency installation is supported only on apt-based Linux hosts." >&2
    exit 1
  fi

  if ! command_exists sudo; then
    echo "sudo is required to install dependencies automatically." >&2
    exit 1
  fi
}

ensure_docker() {
  if command_exists docker && docker compose version >/dev/null 2>&1; then
    return
  fi

  ensure_apt_linux

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

ensure_node_npm() {
  if command_exists node && command_exists npm; then
    return
  fi

  ensure_apt_linux

  echo "Installing Node.js and npm..."
  sudo apt-get update
  sudo apt-get install -y nodejs npm
}

resolve_koda_bin() {
  if command_exists koda; then
    printf '%s\n' "koda"
    return
  fi
  printf '%s\n' "node|${CLI_PACKAGE_DIR}/bin/koda.mjs"
}

install_koda_cli() {
  echo "Installing the local Koda npm CLI..."
  npm install -g "${CLI_PACKAGE_DIR}" >/dev/null
  hash -r
}

main() {
  ensure_docker
  ensure_node_npm
  install_koda_cli

  local koda_bin
  koda_bin="$(resolve_koda_bin)"

  echo "Running Koda product installer through the npm CLI..."
  if [[ "${koda_bin}" == "koda" ]]; then
    koda install \
      --dir "${PRODUCT_DIR}" \
      --manifest "${CLI_PACKAGE_DIR}/release/manifest.json" \
      "$@"
  else
    IFS='|' read -r node_bin cli_bin <<<"${koda_bin}"
    "${node_bin}" "${cli_bin}" install \
      --dir "${PRODUCT_DIR}" \
      --manifest "${CLI_PACKAGE_DIR}/release/manifest.json" \
      "$@"
  fi

  echo
  echo "The source repository remains your dev/source workspace."
  echo "The product/runtime bundle was installed into:"
  echo "  ${PRODUCT_DIR}"
}

main "$@"
