#!/bin/bash
# VPS/worker entrypoint. Runs one calendar cache refresh and one alert poll.
# Intended to be called by systemd timer, cron, or a container scheduler.
set -euo pipefail

PROJECT="${PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$PROJECT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === poll start ==="

if [[ "${RUN_CALENDAR_CACHE:-0}" == "1" ]]; then
  python3 "$PROJECT/update_calendar_cache.py"
else
  echo "[cache] Skipping calendar cache refresh. Set RUN_CALENDAR_CACHE=1 to enable."
fi
# Last-resort kill for a poll that hangs outside the in-process limits. Browser
# checks are capped at 6 minutes in disney_bot.py and login recovery at 6 more,
# so a healthy poll never gets near this. -u keeps the log live if it does.
timeout --kill-after=30 "${POLL_HARD_TIMEOUT_SECS:-780}" python3 -u "$PROJECT/disney_bot.py" --once

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === poll done ==="
