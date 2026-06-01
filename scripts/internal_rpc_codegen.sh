#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
mkdir -p koda/internal_rpc/generated

if ! command -v buf >/dev/null 2>&1; then
  echo "buf is required for internal RPC code generation. Install buf and re-run this script." >&2
  exit 1
fi

buf lint --config buf.yaml
buf generate --template buf.gen.yaml
