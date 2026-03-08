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
if [[ -n "${XHS_ACCOUNT_OVERRIDE:-}" ]]; then
  XHS_ACCOUNT="$XHS_ACCOUNT_OVERRIDE"
fi
XHS_CDP_PORT="${XHS_CDP_PORT:-9333}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

LATEST_JSON="$(ls -1t "$DATA_DIR"/candidates/candidates_*.json 2>/dev/null | head -n1 || true)"
if [[ -z "$LATEST_JSON" ]]; then
  echo "No candidates json found" >&2
  exit 1
fi

TMP_DIR="$DATA_DIR/published/tmp"
mkdir -p "$TMP_DIR"
TITLE_FILE="$TMP_DIR/title.txt"
CONTENT_FILE="$TMP_DIR/content.txt"

"$PYTHON_BIN" - <<PY
import json
f = "$LATEST_JSON"
with open(f, 'r', encoding='utf-8') as fp:
    c = json.load(fp)[0]
open("$TITLE_FILE", "w", encoding="utf-8").write(c["title"].strip())
open("$CONTENT_FILE", "w", encoding="utf-8").write(c["content"].strip())
PY

cd "$XHS_SKILLS_DIR"
CMD=(
  "$PYTHON_BIN" scripts/publish_pipeline.py
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
  RUN_LOG="$TMP_DIR/publish_preview_$(date +%F_%H%M%S).log"
  if "${CMD[@]}" 2>&1 | tee "$RUN_LOG"; then
    PIPE_STATUS=0
  else
    PIPE_STATUS=$?
  fi

  STATUS="FAILED"
  if rg -q "FILL_STATUS: READY_TO_PUBLISH" "$RUN_LOG"; then
    STATUS="READY_TO_PUBLISH"
  fi
  NOTE_LINK="$("$PYTHON_BIN" - <<PY
import re
from pathlib import Path
raw = Path(r"$RUN_LOG").read_text(encoding="utf-8", errors="ignore")
m = re.search(r"Note published at:\\s*(\\S+)", raw)
print(m.group(1) if m else "")
PY
)"

  CANDIDATE_ID="$("$PYTHON_BIN" - <<PY
import json, sqlite3
from pathlib import Path
db = Path(r"$DB_PATH")
if not db.exists():
    print("")
    raise SystemExit(0)
with open(r"$LATEST_JSON", "r", encoding="utf-8") as f:
    first = json.load(f)[0]
batch_date = Path(r"$LATEST_JSON").stem.replace("candidates_", "")
candidate_no = int(first.get("candidate_no", 1))
conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute(
    "SELECT id FROM candidate_posts WHERE batch_date=? AND candidate_no=? ORDER BY id DESC LIMIT 1",
    (batch_date, candidate_no),
)
row = cur.fetchone()
conn.close()
print(row[0] if row else "")
PY
)"

  "$PYTHON_BIN" - <<PY
import sqlite3
from pathlib import Path
db = Path(r"$DB_PATH")
if not db.exists():
    print(f"[publish-record] skip: db not found -> {db}")
    raise SystemExit(0)
raw = Path(r"$RUN_LOG").read_text(encoding="utf-8", errors="ignore")
conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute(
    """
    INSERT INTO publish_records (publish_date, candidate_id, publish_mode, note_link, status, raw_result)
    VALUES (date('now'), ?, ?, ?, ?, ?)
    """,
    (
        int(r"$CANDIDATE_ID") if r"$CANDIDATE_ID".strip() else None,
        "preview",
        r"$NOTE_LINK".strip() or None,
        r"$STATUS",
        raw,
    ),
)
conn.commit()
conn.close()
print("[publish-record] inserted mode=preview")
PY

  if [[ $PIPE_STATUS -ne 0 ]]; then
    exit "$PIPE_STATUS"
  fi
fi
