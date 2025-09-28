#!/usr/bin/env bash
set -euo pipefail

# Simple entry to run spiders inside container
# Usage examples:
#   ./main.sh list --max-pages 1
#   ./main.sh detail --book-ids 100818
#   ./main.sh all --max-pages 5

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure logs directory exists for Scrapy file logging
mkdir -p logs

# Load .env if present (non-fatal if missing)
if [ -f .env ]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' .env | xargs -r) || true
fi

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 {list|detail|comment|all} [args...]" >&2
  echo "Examples:" >&2
  echo "  $0 list --max-pages 1" >&2
  echo "  $0 detail --book-ids 100818,100007" >&2
  exit 2
fi

exec python -u run_spiders.py "$@"

