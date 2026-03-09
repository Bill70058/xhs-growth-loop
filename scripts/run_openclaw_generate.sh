#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "${0%/*}/.." && pwd)"
export ROOT_DIR
ENV_FILE="$ROOT_DIR/config/.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv314/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/usr/bin/python3"
fi

OPENCLAW_URL="${OPENCLAW_CANDIDATE_URL:-http://127.0.0.1:8787/candidates}"
export OPENCLAW_CANDIDATE_ENABLED="${OPENCLAW_CANDIDATE_ENABLED:-1}"
export OPENCLAW_CANDIDATE_URL="$OPENCLAW_URL"
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

health_check() {
  "$PYTHON_BIN" - <<'PY'
from urllib import request
import json, os, sys
url = os.environ.get("OPENCLAW_CANDIDATE_URL", "http://127.0.0.1:8787/candidates")
payload = {"topic": "求职", "candidate_count": 1}
req = request.Request(
    url,
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    r = request.urlopen(req, timeout=2)
    if int(getattr(r, "status", 0)) >= 200 and int(getattr(r, "status", 0)) < 300:
        print("ok")
        sys.exit(0)
except Exception:
    pass
print("down")
sys.exit(1)
PY
}

if ! health_check >/dev/null 2>&1; then
  echo "[openclaw] service down, starting mock daemon..."
  /bin/bash "$ROOT_DIR/scripts/start_openclaw_mock.sh" --daemon
  /bin/sleep 1
fi

if ! health_check >/dev/null 2>&1; then
  echo "[openclaw] service unavailable after startup attempt" >&2
  exit 1
fi

echo "[openclaw] service ready: $OPENCLAW_URL"

run_step analyze_before 0 "$PYTHON_BIN" "$ROOT_DIR/scripts/02_analyze.py"
run_step reward_update 1 "$PYTHON_BIN" "$ROOT_DIR/scripts/06_update_rewards.py"
run_step generate_candidates 0 "$PYTHON_BIN" "$ROOT_DIR/scripts/03_generate_candidates.py"
run_step analyze_after 0 "$PYTHON_BIN" "$ROOT_DIR/scripts/02_analyze.py"
run_step self_audit 1 "$PYTHON_BIN" "$ROOT_DIR/scripts/07_self_audit.py"

if [[ -f "$ROOT_DIR/frontend/package.json" ]]; then
  /usr/bin/env PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
    /opt/homebrew/bin/node /opt/homebrew/lib/node_modules/npm/bin/npm-cli.js \
    --prefix "$ROOT_DIR/frontend" run sync:data >/dev/null 2>&1 || true
fi

"$PYTHON_BIN" - <<'PY'
import json, os
root = os.environ.get("ROOT_DIR", os.getcwd())
p = os.path.join(root, "data", "analysis", "latest_summary.json")
summary = json.load(open(p, "r", encoding="utf-8"))
s = summary.get("strategy_learning", {})
print(json.dumps({
  "run_id": s.get("run_id"),
  "generation_mode": s.get("generation_mode"),
  "openclaw_enabled": s.get("openclaw_enabled"),
  "openclaw_error": s.get("openclaw_error"),
}, ensure_ascii=False))
PY
