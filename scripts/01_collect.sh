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

echo "[collect] start dual-channel collection"
echo "[collect] channel A: own post metrics"
/bin/bash "$ROOT_DIR/scripts/01_collect_own.sh"
echo "[collect] channel B: market learning feeds"
/bin/bash "$ROOT_DIR/scripts/01_collect_market.sh"
echo "[collect] done"
