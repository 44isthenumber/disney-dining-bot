#!/bin/bash
# VPS/worker entrypoint. Runs one calendar cache refresh and one alert poll.
# Intended to be called by systemd timer, cron, or a container scheduler.
set -euo pipefail

PROJECT="${PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$PROJECT"

# Load .env
set -a
# shellcheck disable=SC1091
[ -f "$PROJECT/.env" ] && source "$PROJECT/.env"
set +a

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === poll start ==="

python3 "$PROJECT/update_calendar_cache.py"
python3 "$PROJECT/disney_bot.py" --once

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === poll done ==="
