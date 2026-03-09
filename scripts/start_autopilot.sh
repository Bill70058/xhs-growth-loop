#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "${0%/*}/.." && pwd)"
ENV_FILE="$ROOT_DIR/config/.env"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/autopilot.pid"
LOG_FILE="$LOG_DIR/autopilot_runner.log"
mkdir -p "$LOG_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv314/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/usr/bin/python3"
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[autopilot] already running pid=$OLD_PID"
    exit 0
  fi
fi

nohup "$PYTHON_BIN" "$ROOT_DIR/scripts/openclaw_autopilot.py" >>"$LOG_FILE" 2>&1 &
NEW_PID="$!"
/bin/sleep 1
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "$NEW_PID" > "$PID_FILE"
  echo "[autopilot] started pid=$NEW_PID"
  echo "[autopilot] log=$LOG_FILE"
  exit 0
fi

echo "[autopilot] failed to start, see log: $LOG_FILE" >&2
exit 1
