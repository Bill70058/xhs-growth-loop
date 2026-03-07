#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/config/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

XHS_CDP_PORT="${XHS_CDP_PORT:-9333}"
LEARN_KEYWORDS="${LEARN_KEYWORDS:-跨境卖家学习,小白找工作,面试,小白学AI}"
MARKET_TOP_N="${MARKET_TOP_N:-20}"

if [[ ! -d "$XHS_SKILLS_DIR" ]]; then
  echo "[collect:market] XHS_SKILLS_DIR not found: $XHS_SKILLS_DIR" >&2
  exit 1
fi

TODAY="$(date +%F)"
OUT_DIR="$DATA_DIR/raw/market/$TODAY"
mkdir -p "$OUT_DIR"

IFS=',' read -r -a KEYWORD_ARR <<< "$LEARN_KEYWORDS"

for RAW_KW in "${KEYWORD_ARR[@]}"; do
  KW="$(echo "$RAW_KW" | xargs)"
  [[ -z "$KW" ]] && continue

  SAFE_KW="$(echo "$KW" | sed 's#[/ ]#_#g')"
  RAW_LOG="$OUT_DIR/${SAFE_KW}.raw.log"
  JSON_FILE="$OUT_DIR/${SAFE_KW}.json"

  CMD=(
    python3 scripts/cdp_publish.py
    --account "$XHS_ACCOUNT"
    --port "$XHS_CDP_PORT"
    search-feeds
    --keyword "$KW"
  )

  echo "[collect:market] keyword=$KW"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '[dry-run] %q ' "${CMD[@]}"
    printf '\n'
    continue
  fi

  (cd "$XHS_SKILLS_DIR" && "${CMD[@]}") | tee "$RAW_LOG"

  python3 - <<PY
import json
from pathlib import Path
raw = Path(r"$RAW_LOG").read_text(encoding="utf-8", errors="ignore")
marker = "SEARCH_FEEDS_RESULT:"
idx = raw.find(marker)
if idx == -1:
    payload = {"keyword": r"$KW", "count": 0, "feeds": [], "parse_error": "marker_not_found", "raw_log": r"$RAW_LOG"}
else:
    candidate = raw[idx + len(marker):].strip()
    try:
        payload = json.loads(candidate)
    except Exception as e:
        payload = {"keyword": r"$KW", "count": 0, "feeds": [], "parse_error": str(e), "raw_log": r"$RAW_LOG"}

feeds = payload.get("feeds") if isinstance(payload, dict) else []
if not isinstance(feeds, list):
    feeds = []
payload["feeds"] = feeds[: int(r"$MARKET_TOP_N")]
payload["count"] = len(payload["feeds"])
Path(r"$JSON_FILE").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[collect:market] saved -> {r'$JSON_FILE'} count={payload['count']}")
PY
done

echo "[collect:market] done"
