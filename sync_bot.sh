#!/bin/bash
# Deprecated: the production monitor now runs on a VPS with Playwright.
# Kept only for recovering older local LaunchAgent installs.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=~/Library/Application\ Support/disney-dining-bot

cp "$SRC/.env" \
   "$SRC/update_calendar_cache.py" \
   "$SRC/disney_bot.py" \
   "$SRC/storage.py" \
   "$SRC/auth.py" \
   "$SRC/monitor.py" \
   "$SRC/watch_store.py" \
   "$SRC/notify.py" \
   "$SRC/seed_disney_session.py" \
   "$DEST/"

echo "Synced to $DEST"
echo "Restarting LaunchAgent..."
launchctl unload ~/Library/LaunchAgents/com.disney-dining-bot.plist 2>/dev/null || true
launchctl load  ~/Library/LaunchAgents/com.disney-dining-bot.plist
echo "Done."
