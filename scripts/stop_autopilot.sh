#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "${0%/*}/.." && pwd)"
PID_FILE="$ROOT_DIR/logs/autopilot.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[autopilot] pid file not found"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  rm -f "$PID_FILE"
  echo "[autopilot] empty pid file"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID" || true
  echo "[autopilot] stopped pid=$PID"
else
  echo "[autopilot] process not running pid=$PID"
fi

rm -f "$PID_FILE"
