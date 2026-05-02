# Disney Dining Bot — Claude Context

## What This Project Does
Monitors Walt Disney World restaurant availability and sends SMS alerts when specific dining reservations open. A web UI at **magictablefinder.com** lets you manage the watch list and view a calendar of available dates.

Built and maintained by Craig Owen for personal use (Craig + wife).

---

## Architecture

```
macOS LaunchAgent (every 10 min)
    ├── update_calendar_cache.py  → Chrome (via AppleScript) → Disney API → Gist
    └── disney_bot.py --once      → Chrome (via AppleScript) → Disney API → SMS alert

GitHub Gist (state store — ID: 7e8d8f873715971f8989a25a2f22c089)
    ├── config.yaml       — watch list (restaurants, dates, party sizes)
    ├── tokens.json       — cached Disney JWT (24hr TTL, auto-refreshed)
    ├── bot_state.json    — last poll timestamp + slot count
    └── calendar_{fid}.json  — pre-cached available dates per restaurant

Netlify (magictablefinder.com, site ID: b1f7efc5-da94-4159-ade0-568de33ed24f)
    ├── public/index.html — SPA frontend (login + restaurant browser + calendar)
    └── netlify/functions/api.js — Node.js Lambda, reads/writes Gist
```

---

## The Akamai Problem (Critical)

Disney's CDN (Akamai) blocks ALL Python HTTP requests with HTTP 428 — even with `curl_cffi` Chrome TLS impersonation. The `_abck` cookie is a cryptographic proof-of-work tied to the real Chrome browser session and cannot be replayed.

**The fix:** All Disney API calls must be made from within the real Chrome browser via AppleScript:
1. `osascript` navigates Chrome to the restaurant's Disney page (`/dine-res/restaurant/{slug}`)
2. Waits 5s for Akamai to "solve" the session during page load
3. Injects fresh auth token from Chrome's cookie store into `sessionStorage`
4. Runs `fetch()` from within the page context — succeeds 100%
5. Polls `window._result` every 3s to collect the response

**Key constraint:** Only the **first API call after a fresh page load** succeeds. Navigate to each restaurant's page before fetching its data.

**Chrome requirement:** Chrome must be open with a `disneyworld.disney.go.com` tab. The LaunchAgent is designed for a machine where the user is logged into Disney in Chrome.

**"Allow JavaScript from Apple Events"** must be enabled in Chrome:  
`View → Developer → Allow JavaScript from Apple Events`  
(One-time setup — already done on Craig's machine.)

---

## Key Files

| File | Purpose |
|------|---------|
| `disney_bot.py` | Main polling loop; calls `check_slots_via_chrome()`, deduplicates, sends SMS |
| `monitor.py` | Disney API integration; `check_slots_via_chrome()` uses AppleScript |
| `update_calendar_cache.py` | Caches available date ranges per restaurant to Gist |
| `auth.py` | JWT token lifecycle; reads `TPR-WDW-LBJS.WEB-PROD.token` from Chrome cookies |
| `storage.py` | Gist ↔ local file abstraction; auto-detects mode from env vars |
| `notify.py` | Twilio SMS formatting and sending |
| `netlify/functions/api.js` | All 6 REST endpoints as a single Node.js Lambda |
| `public/index.html` | The entire frontend SPA |
| `sync_bot.sh` | Copies Python files + .env to ~/Library, restarts LaunchAgent |
| `requirements.txt` | Python deps including `browser-cookie3` for Chrome cookie reading |

---

## Running Manually

```bash
cd ~/Documents/disney-dining-bot

# Test the calendar cache update (needs Chrome open on Disney):
python3 update_calendar_cache.py

# Test a full poll (calendar + slot check + potential SMS):
python3 disney_bot.py --once

# Watch live bot logs:
tail -f ~/Library/Logs/disney-dining-bot.log

# After editing any Python file or .env:
bash sync_bot.sh
```

---

## Credentials

All credentials live in `.env` (never committed). Key vars:

```
DISNEY_ACCESS_TOKEN   — Bearer JWT (24hr); auto-refreshed from Chrome cookies
DISNEY_SWID           — Disney account ID
DISNEY_AKACD/ABCK/BM_SZ — Akamai cookies (read live from Chrome; .env is fallback)
API_SECRET            — magictablefinder.com login password
GITHUB_TOKEN          — PAT for Gist read/write
GITHUB_GIST_ID        — 7e8d8f873715971f8989a25a2f22c089
TWILIO_*              — SMS credentials
```

The live auth token is extracted automatically from Chrome's cookie store
(`TPR-WDW-LBJS.WEB-PROD.token`) so `.env` values rarely need manual updates.

---

## magictablefinder.com

- **URL:** https://magictablefinder.com
- **Login:** password is in `.env` as `API_SECRET`
- **Netlify env var** `API_SECRET` must match `.env` value
- After changing the password: update Netlify env var, update `.env`, run `sync_bot.sh`

---

## Deployment

```bash
# Deploy frontend + Netlify function:
git add -A && git commit -m "..." && git push
# Netlify auto-deploys on push to main (via .github/workflows/deploy.yml)

# Sync bot files to LaunchAgent:
bash sync_bot.sh
```

---

## Health Checks

1. `tail -20 ~/Library/Logs/disney-dining-bot.log` — look for "available dates" not "428"
2. `curl -H "X-API-Secret: <password>" https://magictablefinder.com/_api/status` — token_status, last_poll_at
3. Check Gist directly: `https://gist.github.com/7e8d8f873715971f8989a25a2f22c089`

---

## Known Issues / Gotchas

- **No Disney tab open:** `update_calendar_cache.py` will fail with "ERROR: no Disney tab open". Keep a Disney page open in Chrome.
- **Token expired (401):** Auth token is refreshed automatically from the Chrome cookie store. If refresh fails, log into Disney at `disneyworld.disney.go.com` in Chrome and it'll pick up the new token automatically on next poll.
- **428 errors:** Should not happen with the navigate-per-restaurant approach. If seen, check that "Allow JavaScript from Apple Events" is still enabled in Chrome (`View → Developer`).
- **LaunchAgent not running:** `launchctl list | grep disney` — if missing, run `sync_bot.sh`.
- **Gist rate limit:** Rare. Wait a few minutes; the 10-min polling interval prevents this normally.

---

## /disney-poll Skill

There's a `/disney-poll` slash command in `.claude/commands/disney-poll.md`. Invoke it in Claude Code to do an on-demand availability check using Claude's live browser access — bypasses the LaunchAgent entirely.
