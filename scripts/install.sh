#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_PACKAGE_DIR="${ROOT_DIR}/packages/cli"
PRODUCT_DIR="${ROOT_DIR}/.koda-release"
# The npm CLI declares "engines": {"node": ">=20"}.
MIN_NODE_MAJOR=20
NODESOURCE_NODE_MAJOR=22

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

# Print "<distro> <codename>" for Docker's apt repository, read from an
# os-release file (default /etc/os-release). Ubuntu derivatives use their
# Ubuntu base; Debian derivatives use Debian.
docker_apt_repo() {
  local os_release="${1:-/etc/os-release}"
  (
    # shellcheck source=/dev/null
    . "${os_release}"
    local like=" ${ID:-} ${ID_LIKE:-} "
    if [[ "${ID:-}" == "ubuntu" || "${like}" == *" ubuntu "* ]]; then
      printf 'ubuntu %s\n' "${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    elif [[ "${like}" == *" debian "* ]]; then
      printf 'debian %s\n' "${VERSION_CODENAME:-}"
    else
      echo "Automatic Docker installation supports Debian or Ubuntu (and their derivatives); this host is '${ID:-unknown}'. Install Docker with Compose yourself, then re-run this script." >&2
      exit 1
    fi
  )
}

ensure_docker() {
  if command_exists docker && docker compose version >/dev/null 2>&1; then
    return
  fi

  ensure_apt_linux

  local repo distro codename
  repo="$(docker_apt_repo)"
  read -r distro codename <<<"${repo}"

  echo "Installing Docker and Docker Compose..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${distro}/gpg" | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${distro} \
    ${codename} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

node_major_version() {
  local version
  version="$(node --version 2>/dev/null || true)"
  version="${version#v}"
  printf '%s\n' "${version%%.*}"
}

require_supported_node() {
  local major
  major="$(node_major_version)"
  if [[ ! "${major}" =~ ^[0-9]+$ ]] || ((major < MIN_NODE_MAJOR)); then
    echo "Koda needs Node.js ${MIN_NODE_MAJOR} or later; found $(node --version 2>/dev/null || echo 'an unreadable version') at $(command -v node). Upgrade Node.js (for example from https://nodejs.org or NodeSource), then re-run this script." >&2
    exit 1
  fi
}

ensure_node_npm() {
  if command_exists node; then
    # Never replace a Node.js the operator installed; refuse an old one clearly.
    require_supported_node
    if ! command_exists npm; then
      echo "Node.js $(node --version) is installed but npm is missing; install npm for it, then re-run this script." >&2
      exit 1
    fi
    return
  fi

  ensure_apt_linux

  # Distro nodejs packages are older than the CLI needs (12 on Ubuntu 22.04,
  # 18 on 24.04), so install from the NodeSource repository. Its nodejs
  # package ships npm.
  echo "Installing Node.js ${NODESOURCE_NODE_MAJOR} and npm from NodeSource..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  sudo chmod a+r /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODESOURCE_NODE_MAJOR}.x nodistro main" \
    | sudo tee /etc/apt/sources.list.d/nodesource.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y nodejs
  hash -r
  require_supported_node
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

# Run only when executed, so tests can source the functions.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
