#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "${0%/*}/.." && pwd)"
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
  PYTHON_BIN="/usr/bin/python3"
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
    arr = json.load(fp)
if not isinstance(arr, list) or not arr:
    raise SystemExit("candidates json is empty")
chosen = None
for c in arr:
    if isinstance(c, dict) and c.get("selected") is True:
        chosen = c
        break
if chosen is None:
    arr = sorted(arr, key=lambda x: float((x or {}).get("score", 0) or 0), reverse=True)
    chosen = arr[0]
open("$TITLE_FILE", "w", encoding="utf-8").write(chosen["title"].strip())
open("$CONTENT_FILE", "w", encoding="utf-8").write(chosen["content"].strip())
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
  NOTE_ID="$("$PYTHON_BIN" - <<PY
import re
from urllib.parse import parse_qs, urlparse
from pathlib import Path
note_link = r"$NOTE_LINK".strip()
raw = Path(r"$RUN_LOG").read_text(encoding="utf-8", errors="ignore")
note_id = ""
if note_link:
    try:
        u = urlparse(note_link)
        q = parse_qs(u.query or "")
        for key in ("note_id", "noteId", "id"):
            vals = q.get(key) or []
            if vals and str(vals[0]).strip():
                note_id = str(vals[0]).strip()
                break
        if not note_id:
            m = re.search(r"/(?:explore|discovery/item|note)/([0-9A-Za-z_-]{8,64})", u.path or "")
            if m:
                note_id = m.group(1)
    except Exception:
        pass
if not note_id:
    for p in (
        r'"note_id"\\s*:\\s*"([0-9A-Za-z_-]{8,64})"',
        r'"noteId"\\s*:\\s*"([0-9A-Za-z_-]{8,64})"',
        r'"post_id"\\s*:\\s*"([0-9A-Za-z_-]{8,64})"',
    ):
        m = re.search(p, raw)
        if m:
            note_id = m.group(1)
            break
print(note_id)
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
    arr = json.load(f)
if not isinstance(arr, list) or not arr:
    print("")
    raise SystemExit(0)
chosen = None
for c in arr:
    if isinstance(c, dict) and c.get("selected") is True:
        chosen = c
        break
if chosen is None:
    arr = sorted(arr, key=lambda x: float((x or {}).get("score", 0) or 0), reverse=True)
    chosen = arr[0]
batch_date = Path(r"$LATEST_JSON").stem.replace("candidates_", "")
candidate_no = int(chosen.get("candidate_no", 1))
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
cur.execute("PRAGMA table_info(publish_records)")
cols = {r[1] for r in cur.fetchall()}
if "note_id" not in cols:
    cur.execute("ALTER TABLE publish_records ADD COLUMN note_id TEXT")
cur.execute(
    """
    INSERT INTO publish_records (publish_date, candidate_id, publish_mode, note_link, note_id, status, raw_result)
    VALUES (date('now'), ?, ?, ?, ?, ?, ?)
    """,
    (
        int(r"$CANDIDATE_ID") if r"$CANDIDATE_ID".strip() else None,
        "preview",
        r"$NOTE_LINK".strip() or None,
        r"$NOTE_ID".strip() or None,
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
