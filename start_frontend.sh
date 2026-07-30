#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm was not found in PATH. Install Node.js 20 or newer first." >&2
  echo "After installing Node.js, run: npm install" >&2
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/node_modules" ]]; then
  echo "Error: frontend dependencies are not installed." >&2
  echo "Run: npm install" >&2
  exit 1
fi

FRONTEND_HOST="${SIMLAB_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${SIMLAB_FRONTEND_PORT:-5173}"
BACKEND_HOST="${SIMLAB_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${SIMLAB_BACKEND_PORT:-8765}"

export SIMLAB_API_PROXY_TARGET="${SIMLAB_API_PROXY_TARGET:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

echo "Starting SimLab frontend at http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "Proxying API and WebSocket requests to ${SIMLAB_API_PROXY_TARGET}"

exec npm run dev:frontend -- \
  --host "${FRONTEND_HOST}" \
  --port "${FRONTEND_PORT}" \
  "$@"
