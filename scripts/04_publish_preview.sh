#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/config/.env"

# shellcheck disable=SC1090
source "$ENV_FILE"
XHS_CDP_PORT="${XHS_CDP_PORT:-9333}"

LATEST_JSON="$(ls -1t "$DATA_DIR"/candidates/candidates_*.json 2>/dev/null | head -n1 || true)"
if [[ -z "$LATEST_JSON" ]]; then
  echo "No candidates json found" >&2
  exit 1
fi

TMP_DIR="$DATA_DIR/published/tmp"
mkdir -p "$TMP_DIR"
TITLE_FILE="$TMP_DIR/title.txt"
CONTENT_FILE="$TMP_DIR/content.txt"

python3 - <<PY
import json
f = "$LATEST_JSON"
with open(f, 'r', encoding='utf-8') as fp:
    c = json.load(fp)[0]
open("$TITLE_FILE", "w", encoding="utf-8").write(c["title"].strip())
open("$CONTENT_FILE", "w", encoding="utf-8").write(c["content"].strip())
PY

cd "$XHS_SKILLS_DIR"
CMD=(
  python3 scripts/publish_pipeline.py
  --account "$XHS_ACCOUNT"
  --port "$XHS_CDP_PORT"
  --preview
  --title-file "$TITLE_FILE"
  --content-file "$CONTENT_FILE"
  --image-urls "https://picsum.photos/1200/1200"
)

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf '[dry-run] %q ' "${CMD[@]}"
  printf '\n'
else
  "${CMD[@]}"
fi
