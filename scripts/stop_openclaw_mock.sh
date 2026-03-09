#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "${0%/*}/.." && pwd)"
PID_FILE="$ROOT_DIR/logs/openclaw_mock.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[openclaw-mock] pid file not found"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  echo "[openclaw-mock] empty pid file"
  rm -f "$PID_FILE"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "[openclaw-mock] stopped pid=$PID"
else
  echo "[openclaw-mock] process not running pid=$PID"
fi

rm -f "$PID_FILE"
