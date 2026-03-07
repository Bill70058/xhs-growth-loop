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
CONTENT_PAGE_NUM="${CONTENT_PAGE_NUM:-1}"
CONTENT_PAGE_SIZE="${CONTENT_PAGE_SIZE:-10}"
CONTENT_NOTE_TYPE="${CONTENT_NOTE_TYPE:-0}"

mkdir -p "$DATA_DIR/raw" "$ROOT_DIR/logs"
TODAY="$(date +%F)"
CSV_FILE="$DATA_DIR/raw/content_data_${TODAY}.csv"
JSON_FILE="$DATA_DIR/raw/content_data_${TODAY}.json"

if [[ ! -d "$XHS_SKILLS_DIR" ]]; then
  echo "[collect:own] XHS_SKILLS_DIR not found: $XHS_SKILLS_DIR" >&2
  exit 1
fi

CMD=(
  python3 scripts/cdp_publish.py
  --account "$XHS_ACCOUNT"
  --port "$XHS_CDP_PORT"
  content-data
  --page-num "$CONTENT_PAGE_NUM"
  --page-size "$CONTENT_PAGE_SIZE"
  --type "$CONTENT_NOTE_TYPE"
  --csv-file "$CSV_FILE"
)

echo "[collect:own] ${CMD[*]}"
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf '[dry-run] %q ' "${CMD[@]}"
  printf '\n'
  exit 0
fi

# Keep raw command output for troubleshooting and reuse
(cd "$XHS_SKILLS_DIR" && "${CMD[@]}") | tee "$JSON_FILE"

echo "[collect:own] done -> $CSV_FILE"
