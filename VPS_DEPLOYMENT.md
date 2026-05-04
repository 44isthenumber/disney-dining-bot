# VPS Deployment

This project now runs like a self-hosted MouseWatcher:

- Netlify hosts `magictablefinder.com`.
- Gist stores watches, status, calendar caches, `open_slots.json`, and alert history.
- A low-cost VPS runs the Playwright polling worker every 10 minutes.
- Twilio texts/WhatsApps the user who created each watch.

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
WATCH_USERS='{"craig":{"name":"Craig","password":"...","phone":"whatsapp:+1..."},"Jessica":{"name":"Jessica","password":"...","phone":"whatsapp:+1..."}}'
GITHUB_GIST_ID=7e8d8f873715971f8989a25a2f22c089
GITHUB_TOKEN=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM=whatsapp:+1...      # or +1... for regular SMS
DISNEY_BROWSER_PROFILE_DIR=/opt/disney-dining-bot/.browser-profile
DISNEY_HEADLESS=true
```

Netlify needs the same `WATCH_USERS`, `GITHUB_GIST_ID`, `GITHUB_TOKEN`, and legacy `API_SECRET` fallback if you keep it.
If WATCH_USERS is not set in Netlify, it will use FALLBACK_USERS (default: craig and Jessica profiles without phones) for public profile exposure.

## 3. Seed Disney Session

```bash
cd /opt/disney-dining-bot
. .venv/bin/activate
DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py
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
python3 scripts/smoke_test_api.py --user-id craig
python3 scripts/smoke_test_api.py --user-id Jessica
```

If `session_status` is `needs_attention`, run `seed_disney_session.py` again.

## 6. Dedicated Disney Login

For a dedicated bot-only MyDisney account, store credentials only in the VPS
`.env` file:

```bash
DISNEY_LOGIN_EMAIL=bot-account@example.com
DISNEY_LOGIN_PASSWORD=change-me
```

Then run:

```bash
DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py
```

The script attempts the login, navigates to a dining page, and verifies the
Disney auth cookie. If Disney presents MFA, CAPTCHA, passkey, or security
checks, complete that step manually in the opened browser and press Enter.

## 7. Alert State Safety

The worker alerts only for slots that are open now but were absent in the previous poll. That baseline lives in `open_slots.json`.

Important:

- Do not delete or clear `open_slots.json` casually. If it is missing, the worker baselines current openings without alerting.
- `seen_slots.json` is alert history/audit, not the primary dedupe mechanism.
- The stable dedupe key excludes Disney `offerId`, because Disney can rotate `offerId` for the same visible time.
- If changing alert semantics, stop the timer first:

```bash
sudo systemctl stop disney-dining-bot.timer
# deploy/test/baseline carefully
sudo systemctl start disney-dining-bot.timer
```

Manual worker polls must use Xvfb:

```bash
cd /opt/disney-dining-bot
. .venv/bin/activate
xvfb-run -a python3 disney_bot.py --once
```
