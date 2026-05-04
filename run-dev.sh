#!/usr/bin/env bash
# Dev servers for BioAPEX (requires Python 3.10+ and Node).
# Uses /gpfs/scrubbed/jedels/miniAgent/.py311 and .node-env by default.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

is_pid_live() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

listener_pids_for_port() {
  local port="$1"
  ss -ltnpH "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true
}

cleanup_pid_file() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(tr -d '[:space:]' < "$pid_file")"
  if ! is_pid_live "$pid"; then
    rm -f "$pid_file"
  fi
}

stop_listener_on_port() {
  local port="$1"
  local label="$2"
  local pids
  pids="$(listener_pids_for_port "$port" | tr '\n' ' ')"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Stopping existing $label listener(s) on port $port: $pids"
  kill $pids 2>/dev/null || true
}

PY_ENV="${BIOAPEX_PY_ENV:-$ROOT/.py311}"
NODE_ENV="${BIOAPEX_NODE_ENV:-$ROOT/.node-env}"

if [[ ! -x "$PY_ENV/bin/python" ]]; then
  if ! command -v conda &>/dev/null; then
    if [[ -f /gpfs/software/miniforge3/25.3.1-3/etc/profile.d/conda.sh ]]; then
      # shellcheck source=/dev/null
      source /gpfs/software/miniforge3/25.3.1-3/etc/profile.d/conda.sh
    else
      echo "conda not found; install Python 3.11+ at BIOAPEX_PY_ENV=$PY_ENV"
      exit 1
    fi
  fi
  echo "Creating Python env at $PY_ENV (3.11)..."
  conda create -y -p "$PY_ENV" python=3.11 pip -c conda-forge
  "$PY_ENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
fi

if [[ ! -x "$NODE_ENV/bin/npm" ]]; then
  if ! command -v conda &>/dev/null; then
    if [[ -f /gpfs/software/miniforge3/25.3.1-3/etc/profile.d/conda.sh ]]; then
      # shellcheck source=/dev/null
      source /gpfs/software/miniforge3/25.3.1-3/etc/profile.d/conda.sh
    fi
  fi
  echo "Creating Node env at $NODE_ENV..."
  conda create -y -p "$NODE_ENV" nodejs -c conda-forge
fi

export PATH="$NODE_ENV/bin:$PATH"

RUN_USER="${USER:-$(id -un)}"
API_PORT="${BIOAPEX_API_PORT:-8022}"
WEB_PORT="${BIOAPEX_WEB_PORT:-3022}"
BACKEND_PID_FILE="$LOG_DIR/backend-${RUN_USER}.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend-${RUN_USER}.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend-${RUN_USER}-${API_PORT}.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend-${RUN_USER}-${WEB_PORT}.log"
FRONTEND_DIST_DIR="${NEXT_DIST_DIR:-.next-dev}"
FRONTEND_DIST_PATH="$FRONTEND_DIR/$FRONTEND_DIST_DIR"
FRONTEND_ENTRY="$FRONTEND_DIR/node_modules/next/dist/bin/next"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  (cd "$FRONTEND_DIR" && npm install)
fi

test -f "$BACKEND_DIR/.env" || cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"

cleanup_pid_file "$BACKEND_PID_FILE"
cleanup_pid_file "$FRONTEND_PID_FILE"
stop_listener_on_port "$API_PORT" "backend"
stop_listener_on_port "$WEB_PORT" "frontend"

if [[ -d "$FRONTEND_DIST_PATH" ]]; then
  echo "Removing stale frontend dev build at $FRONTEND_DIST_PATH"
  if ! rm -rf "$FRONTEND_DIST_PATH"; then
    FRONTEND_DIST_DIR=".next-dev-$RANDOM-$$"
    FRONTEND_DIST_PATH="$FRONTEND_DIR/$FRONTEND_DIST_DIR"
    echo "Warning: cleanup was incomplete; using fresh frontend dist dir $FRONTEND_DIST_DIR"
  fi
fi

echo "Starting backend on 0.0.0.0:$API_PORT ..."
nohup bash -c "cd \"$BACKEND_DIR\" && exec \"$PY_ENV/bin/uvicorn\" app:app --host 0.0.0.0 --port \"$API_PORT\"" \
  >"$BACKEND_LOG_FILE" 2>&1 &
echo $! >"$BACKEND_PID_FILE"

echo "Starting frontend on 0.0.0.0:$WEB_PORT (API port $API_PORT) ..."
(
  cd "$FRONTEND_DIR"
  export NEXT_PUBLIC_API_PORT="$API_PORT"
  nohup env NEXT_DIST_DIR="$FRONTEND_DIST_DIR" NEXT_PUBLIC_API_PORT="$API_PORT" \
    "$NODE_ENV/bin/node" "$FRONTEND_ENTRY" dev --hostname 0.0.0.0 --port "$WEB_PORT" \
    >"$FRONTEND_LOG_FILE" 2>&1 &
  echo $! >"$FRONTEND_PID_FILE"
)

sleep 2
echo "URLs: http://127.0.0.1:$WEB_PORT  (API http://127.0.0.1:$API_PORT)"
echo "Logs: $BACKEND_LOG_FILE  $FRONTEND_LOG_FILE"
tail -5 "$BACKEND_LOG_FILE" || true
tail -8 "$FRONTEND_LOG_FILE" || true
