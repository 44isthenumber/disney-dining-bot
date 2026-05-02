# VPS Deployment

This project now runs like a self-hosted MouseWatcher:

- Netlify hosts `magictablefinder.com`.
- Gist stores watches, status, calendar caches, and seen-slot state.
- A low-cost VPS runs the Playwright polling worker every 10 minutes.
- Twilio texts the user who created each watch.

## 1. Install Runtime

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip
git clone <repo-url> /opt/disney-dining-bot
cd /opt/disney-dining-bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install --with-deps chromium
```

## 2. Configure `.env`

Copy `.env.template` to `.env` and set:

```bash
WATCH_USERS='{"craig":{"name":"Craig","password":"...","phone":"+1..."},"wife":{"name":"Wife","password":"...","phone":"+1..."}}'
GITHUB_GIST_ID=7e8d8f873715971f8989a25a2f22c089
GITHUB_TOKEN=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM=+1...
DISNEY_BROWSER_PROFILE_DIR=/opt/disney-dining-bot/.browser-profile
DISNEY_HEADLESS=true
```

Netlify needs the same `WATCH_USERS`, `GITHUB_GIST_ID`, `GITHUB_TOKEN`, and legacy `API_SECRET` fallback if you keep it.

## 3. Seed Disney Session

```bash
cd /opt/disney-dining-bot
. .venv/bin/activate
DISNEY_HEADLESS=false python3 seed_disney_session.py
```

Log into Disney in the browser that opens, then press Enter in the terminal. The worker reuses that profile.

## 4. Install Timer

```bash
sudo useradd --system --home /opt/disney-dining-bot --shell /usr/sbin/nologin disneybot || true
sudo chown -R disneybot:disneybot /opt/disney-dining-bot
sudo cp deploy/disney-dining-bot.service /etc/systemd/system/
sudo cp deploy/disney-dining-bot.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now disney-dining-bot.timer
```

## 5. Check Health

```bash
journalctl -u disney-dining-bot.service -n 100
curl -H "X-User-Id: craig" -H "X-API-Secret: <craig-password>" https://magictablefinder.com/_api/status
```

If `session_status` is `needs_attention`, run `seed_disney_session.py` again.
