#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Error: Python virtual environment was not found at ${VENV_PYTHON}." >&2
  echo "Create it with: python3 -m venv .venv" >&2
  echo "Then install the backend with: .venv/bin/python -m pip install -e ." >&2
  exit 1
fi

BACKEND_HOST="${SIMLAB_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${SIMLAB_BACKEND_PORT:-8765}"
DATA_ROOT="${SIMLAB_DATA_ROOT:-${SCRIPT_DIR}/.simlab-data}"
LOCAL_SCENE_ROOT="${SIMLAB_LOCAL_SCENE_ROOT:-${SCRIPT_DIR}/external/architectural-brownstone/unpacked}"
ALGORITHM_HOST="${SIMLAB_ALGORITHM_HOST:-127.0.0.1}"
ALGORITHM_PORT="${SIMLAB_ALGORITHM_PORT:-50051}"
if [[ -n "${SIMLAB_ALGORITHM_BIND:-}" ]]; then
  ALGORITHM_BIND="${SIMLAB_ALGORITHM_BIND}"
  ALGORITHM_PORT="${ALGORITHM_BIND##*:}"
else
  ALGORITHM_BIND="${ALGORITHM_HOST}:${ALGORITHM_PORT}"
fi
ALGORITHM_ASSET_ROOT="${SIMLAB_ALGORITHM_ASSET_ROOT:-${SCRIPT_DIR}}"
ALGORITHM_WORKERS="${SIMLAB_ALGORITHM_WORKERS:-8}"

export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

if ! [[ "${BACKEND_PORT}" =~ ^[0-9]+$ ]]; then
  echo "Error: SIMLAB_BACKEND_PORT must be a number: ${BACKEND_PORT}" >&2
  exit 1
fi
if ! [[ "${ALGORITHM_PORT}" =~ ^[0-9]+$ ]]; then
  echo "Error: SIMLAB_ALGORITHM_PORT must be a number: ${ALGORITHM_PORT}" >&2
  exit 1
fi
if ! [[ "${ALGORITHM_WORKERS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "Error: SIMLAB_ALGORITHM_WORKERS must be a positive integer." >&2
  exit 1
fi

if ! "${VENV_PYTHON}" -c "import fastapi, grpc, mujoco, uvicorn" >/dev/null 2>&1; then
  echo "Error: backend dependencies are incomplete." >&2
  echo "Install them with: .venv/bin/python -m pip install -e '.[algorithm,remote]'" >&2
  exit 1
fi

port_is_listening() {
  local port="$1"
  ss -H -ltn "sport = :${port}" | grep -q .
}

if port_is_listening "${BACKEND_PORT}"; then
  echo "Error: API port ${BACKEND_PORT} is already in use." >&2
  exit 1
fi
if port_is_listening "${ALGORITHM_PORT}"; then
  echo "Error: algorithm gRPC port ${ALGORITHM_PORT} is already in use." >&2
  exit 1
fi

api_pid=""
algorithm_pid=""

stop_process() {
  local pid="$1"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill -TERM "${pid}" 2>/dev/null || true
  fi
}

cleanup() {
  trap - EXIT INT TERM
  stop_process "${api_pid}"
  stop_process "${algorithm_pid}"
  [[ -z "${api_pid}" ]] || wait "${api_pid}" 2>/dev/null || true
  [[ -z "${algorithm_pid}" ]] || wait "${algorithm_pid}" 2>/dev/null || true
}

handle_signal() {
  exit 130
}

trap cleanup EXIT
trap handle_signal INT TERM

echo "Starting SimLab API backend at http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "Starting MuJoCo algorithm gRPC backend at ${ALGORITHM_BIND}"
echo "API data directory: ${DATA_ROOT}"
if [[ -f "${LOCAL_SCENE_ROOT}/Demos/AEC/BrownstoneDemo/World_BrownstoneDemopack_Park(8Gb).usd" ]]; then
  LOCAL_SCENE_ARGS=(--local-scene-root "${LOCAL_SCENE_ROOT}")
  echo "Local Park scene root: ${LOCAL_SCENE_ROOT}"
else
  LOCAL_SCENE_ARGS=()
  echo "Local Park scene: disabled (pack not found at ${LOCAL_SCENE_ROOT})"
fi
echo "Algorithm asset root: ${ALGORITHM_ASSET_ROOT}"

"${VENV_PYTHON}" -u -m simlab.web_server \
  --host "${BACKEND_HOST}" \
  --port "${BACKEND_PORT}" \
  --data-root "${DATA_ROOT}" \
  --seed-assets "${SCRIPT_DIR}/assets" \
  "${LOCAL_SCENE_ARGS[@]}" \
  --cors-origin "http://127.0.0.1:5173" \
  --cors-origin "http://localhost:5173" \
  --cors-origin "http://127.0.0.1:4173" \
  --cors-origin "http://localhost:4173" \
  "$@" &
api_pid=$!

"${VENV_PYTHON}" -u -m simlab.simulation.grpc_backend \
  --bind "${ALGORITHM_BIND}" \
  --asset-root "${ALGORITHM_ASSET_ROOT}" \
  --workers "${ALGORITHM_WORKERS}" &
algorithm_pid=$!

api_health_host="${BACKEND_HOST}"
if [[ "${api_health_host}" == "0.0.0.0" ]]; then
  api_health_host="127.0.0.1"
fi

api_ready=false
for _ in {1..50}; do
  if ! kill -0 "${api_pid}" 2>/dev/null; then
    echo "Error: API backend exited during startup." >&2
    exit 1
  fi
  if curl --fail --silent --max-time 1 \
    "http://${api_health_host}:${BACKEND_PORT}/api/v1/health" >/dev/null; then
    api_ready=true
    break
  fi
  sleep 0.1
done
if [[ "${api_ready}" != "true" ]]; then
  echo "Error: API health check timed out." >&2
  exit 1
fi

algorithm_ready=false
for _ in {1..50}; do
  if ! kill -0 "${algorithm_pid}" 2>/dev/null; then
    echo "Error: algorithm gRPC backend exited during startup." >&2
    exit 1
  fi
  if port_is_listening "${ALGORITHM_PORT}"; then
    algorithm_ready=true
    break
  fi
  sleep 0.1
done
if [[ "${algorithm_ready}" != "true" ]]; then
  echo "Error: algorithm gRPC readiness check timed out." >&2
  exit 1
fi

echo "SimLab backend is ready. Press Ctrl+C to stop both services."

set +e
wait -n "${api_pid}" "${algorithm_pid}"
exit_status=$?
set -e

if ! kill -0 "${api_pid}" 2>/dev/null; then
  echo "API backend stopped; shutting down the algorithm backend." >&2
else
  echo "Algorithm backend stopped; shutting down the API backend." >&2
fi
exit "${exit_status}"
