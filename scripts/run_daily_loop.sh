#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_$(date +%F_%H%M%S).log"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

{
  echo "=== START $(date) ==="
  bash "$ROOT_DIR/scripts/01_collect.sh"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/02_analyze.py"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/03_generate_candidates.py"
  bash "$ROOT_DIR/scripts/04_publish_preview.sh"
  echo "=== END $(date) ==="
} | tee "$LOG_FILE"

echo "Daily loop log: $LOG_FILE"
