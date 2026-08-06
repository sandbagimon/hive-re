#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Error: Python virtual environment was not found at ${VENV_PYTHON}." >&2
  echo "Create it with: python3 -m venv .venv" >&2
  exit 1
fi

if ! "${VENV_PYTHON}" -c "import httpx, mcp, simlab.mcp.server" >/dev/null 2>&1; then
  echo "Error: MCP dependencies are incomplete." >&2
  echo "Install them with: .venv/bin/python -m pip install -e '.[mcp]'" >&2
  exit 1
fi

export SIMLAB_API_URL="${SIMLAB_API_URL:-http://127.0.0.1:8765}"
export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

echo "Starting SimLab MCP adapter (${SIMLAB_MCP_TRANSPORT:-stdio})" >&2
echo "Connecting to SimLab API at ${SIMLAB_API_URL}" >&2

exec "${VENV_PYTHON}" -m simlab.mcp.server "$@"
