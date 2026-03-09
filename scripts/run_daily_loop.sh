#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "${0%/*}/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_$(date +%F_%H%M%S).log"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/usr/bin/python3"
fi
export OPENCLAW_RUNTIME_ENABLED="${OPENCLAW_RUNTIME_ENABLED:-1}"
RUNTIME_MAX_RETRIES="${OPENCLAW_RUNTIME_MAX_RETRIES:-2}"

run_step() {
  local step_id="$1"
  local soft="${2:-0}"
  shift 2
  if [[ "$soft" == "1" ]]; then
    "$PYTHON_BIN" "$ROOT_DIR/scripts/openclaw_runtime_bridge.py" \
      --step-id "$step_id" \
      --max-retries "$RUNTIME_MAX_RETRIES" \
      --soft-fail \
      -- "$@"
  else
    "$PYTHON_BIN" "$ROOT_DIR/scripts/openclaw_runtime_bridge.py" \
      --step-id "$step_id" \
      --max-retries "$RUNTIME_MAX_RETRIES" \
      -- "$@"
  fi
}

{
  echo "=== START $(date) ==="
  run_step healthcheck 1 "$PYTHON_BIN" "$ROOT_DIR/scripts/00_healthcheck.py"
  /bin/bash "$ROOT_DIR/scripts/01_collect.sh"
  run_step analyze_before 0 "$PYTHON_BIN" "$ROOT_DIR/scripts/02_analyze.py"
  run_step reward_update 1 "$PYTHON_BIN" "$ROOT_DIR/scripts/06_update_rewards.py"
  run_step generate_candidates 0 "$PYTHON_BIN" "$ROOT_DIR/scripts/03_generate_candidates.py"
  run_step self_audit 1 "$PYTHON_BIN" "$ROOT_DIR/scripts/07_self_audit.py"
  /bin/bash "$ROOT_DIR/scripts/04_publish_preview.sh"
  echo "=== END $(date) ==="
} | tee "$LOG_FILE"

echo "Daily loop log: $LOG_FILE"
