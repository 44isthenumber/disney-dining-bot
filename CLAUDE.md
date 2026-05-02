# Disney Dining Bot — Claude Context

## What This Project Does
Self-hosted MouseWatcher-style service for Walt Disney World dining. A web UI at **magictablefinder.com** lets each user manage their own watch list; a VPS worker polls Disney and sends SMS alerts to the user who created the watch.

Built and maintained by Craig Owen for personal use (Craig + wife).

---

## Architecture

```
VPS systemd timer (every 10 min)
    ├── update_calendar_cache.py  → Playwright Chrome profile → Disney API → Gist
    └── disney_bot.py --once      → Playwright Chrome profile → Disney API → owner-specific SMS alert

GitHub Gist (state store — ID: 7e8d8f873715971f8989a25a2f22c089)
    ├── watches.json       — owner-scoped watch records
    ├── config.yaml        — legacy grouped watch list, read only for migration/fallback
    ├── bot_state.json     — last poll timestamp + health state
    ├── seen_slots.json    — persisted alert deduplication state
    └── calendar_{fid}.json  — pre-cached available dates per restaurant

Netlify (magictablefinder.com, site ID: b1f7efc5-da94-4159-ade0-568de33ed24f)
    ├── public/index.html — SPA frontend (profile login + restaurant browser + calendar)
    └── netlify/functions/api.js — Node.js Lambda, reads/writes Gist
```

---

## The Akamai Problem (Critical)

Disney's CDN (Akamai) blocks Python HTTP requests with HTTP 428. The `_abck` cookie is tied to a real browser session and cannot be replayed reliably.

**The fix:** All Disney API calls run inside a persistent Playwright Chrome profile on the VPS:
1. Playwright navigates Chrome to `/dine-res/restaurant/{slug}`.
2. Waits for Akamai/browser session warm-up.
3. Reads the Disney auth token from the Playwright profile cookies.
4. Runs `fetch()` from within the page context.

**Key constraint:** only the first API call after a fresh page load is reliable. Navigate to each restaurant page before fetching its data.

**Session requirement:** the VPS Playwright profile must be logged into Disney. If Disney expires or challenges the session, run `DISNEY_HEADLESS=false python3 seed_disney_session.py` on the VPS and log in again.

---

## Key Files

| File | Purpose |
|------|---------|
| `disney_bot.py` | Main polling loop; reads owner-scoped watches, deduplicates, sends SMS |
| `watch_store.py` | Owner/profile-aware watch storage; migrates legacy `config.yaml` |
| `monitor.py` | Disney API integration; `check_slots_via_playwright()` uses hosted Chrome |
| `update_calendar_cache.py` | Caches available date ranges per restaurant to Gist |
| `storage.py` | Gist/local file abstraction |
| `notify.py` | Twilio SMS formatting and owner-specific delivery |
| `netlify/functions/api.js` | REST endpoints for status, profiles, restaurants, calendars, watches |
| `public/index.html` | Frontend SPA |
| `seed_disney_session.py` | Opens the VPS Playwright profile for manual Disney login |
| `deploy/` | systemd service/timer templates for the VPS worker |

---

## Running Manually

```bash
cd ~/Documents/disney-dining-bot

python3 -m playwright install chromium

# Seed or repair Disney login session:
DISNEY_HEADLESS=false python3 seed_disney_session.py

# Test the calendar cache update:
python3 update_calendar_cache.py

# Test a full poll:
python3 disney_bot.py --once
```

---

## Credentials

All credentials live in `.env` (never committed). Key vars:

```
WATCH_USERS — JSON mapping user IDs to {name,password,phone}
API_SECRET — legacy shared login fallback
GITHUB_TOKEN — PAT for Gist read/write
GITHUB_GIST_ID — 7e8d8f873715971f8989a25a2f22c089
TWILIO_* — SMS credentials
DISNEY_BROWSER_PROFILE_DIR — persistent Playwright profile path
DISNEY_HEADLESS — true for normal worker, false for manual login seeding
```

---

## Deployment

```bash
# Deploy frontend + Netlify function:
git add -A && git commit -m "..." && git push

# VPS worker:
sudo cp deploy/disney-dining-bot.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now disney-dining-bot.timer
```

---

## Health Checks

1. `journalctl -u disney-dining-bot.service -n 100` — look for successful Playwright polls.
2. `curl -H "X-User-Id: craig" -H "X-API-Secret: <password>" https://magictablefinder.com/_api/status` — check `session_status`, `last_poll_at`, and `last_errors`.
3. Check Gist directly: `https://gist.github.com/7e8d8f873715971f8989a25a2f22c089`

---

## Known Issues / Gotchas

- **Disney session expired:** run `DISNEY_HEADLESS=false python3 seed_disney_session.py` on the VPS and log in.
- **428 errors:** re-seed the VPS browser session and verify `DISNEY_BROWSER_PROFILE_DIR` persists across worker runs.
- **Worker not running:** `systemctl status disney-dining-bot.timer`.
- **Gist rate limit/conflict:** rare. Wait a few minutes; the 10-minute polling interval should avoid this normally.
