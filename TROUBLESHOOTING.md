# Troubleshooting — Disney Dining Bot

A runbook for diagnosing the bot from the VPS without reading any source. Read top to bottom; each section is self-contained.

VPS: `root@107.170.35.91`, SSH key `~/.ssh/disney_dining_vps`, app at `/opt/disney-dining-bot`.

## At-a-glance: alert channels

| Alert source | Trigger | Goes to | Channel |
|---|---|---|---|
| Bot's Signal alert (in-process) | Disney session lost; Login Agent failed | Craig only | Signal (`+19852359090` "Magic Table Finder" → Craig) |
| Reservation match | New opening on a watch | Watch's owner only | Signal |
| UptimeRobot | `/_api/health` returns non-200 for >5 min, or no response for >30 min | `craig@sco.gs` | Email |

If you haven't gotten an alert and feel anxious: hit https://magictablefinder.com/_api/health from any browser. `"ok":true` means the bot is healthy — Disney just doesn't have anything matching your watches yet.

---

## 1. Quick health check

```bash
ssh -i ~/.ssh/disney_dining_vps root@107.170.35.91
cd /opt/disney-dining-bot
systemctl is-active disney-dining-bot.timer    # should be "active"
journalctl -u disney-dining-bot.service -n 50 --no-pager
```

A healthy poll looks like:

```
=== poll start ===
Polling 21 watch(es) across 2 restaurant request(s) …
[monitor] Space 220 Lounge: no availability returned by Disney.
[bot] Space 220 Lounge: no availability.
[bot] No newly opened slots to alert on.
=== poll done ===
```

"No availability" is **normal** — it just means Disney has nothing matching your watches right now. It is *not* an error.

If polls succeed but you expect alerts, that's a watch/criteria question, not a bot health question. Skip the rest of this doc and check `magictablefinder.com`.

---

## 2. Failure modes (what to look for in journalctl)

The bot has three known classes of failure. Grep the logs and match the pattern.

### 2.1 Disney session genuinely expired (most common)

```
[bot] Check failed for Space 220 Lounge: Disney auth required:
  token cookie present but not refreshable; ...
```

Plus, near it, one of:
- `[auth] Disney cookie token expires in -NNNNs — refreshing.` (negative seconds = past expiry)
- `[auth] refresh non-200: HTTP 403 from https://auth.registerdisney.go.com/...`

**Diagnosis:** the persistent Chrome profile's Disney cookie expired or was invalidated. Disney's refresh endpoint (`auth.registerdisney.go.com/.../refreshAuth`) currently returns Akamai 403 for everyone — that endpoint is effectively dead, so we cannot refresh programmatically. The session must be re-established via a real browser login.

**Fix:** re-seed (see §3).

### 2.2 Login Agent failing to recover automatically

```
[bot] Disney auth error detected — activating Login Agent...
[recovery] Attempting automatic Disney session recovery...
[recovery] Recovery failed (exit 1). Full log: /var/log/disney-dining-bot/last-recovery.log...
```

**First read the full recovery log:**

```bash
cat /var/log/disney-dining-bot/last-recovery.log
```

Common patterns inside:

| Recovery-log pattern | What it means | Fix |
|---|---|---|
| `net::ERR_HTTP2_PROTOCOL_ERROR` | Akamai detected headless Chromium and aborted | Confirm `DISNEY_HEADLESS=false` in `.env` and that recovery subprocess is not overriding it (see §6) |
| `Could not find a visible email field` | Disney login page selectors changed, or page didn't load | Manually re-seed in a TTY (§3); update selectors in `seed_disney_session.py` if persistent |
| `additional verification step required` | MFA / CAPTCHA / passkey was prompted | Manually re-seed in a TTY (§3) and complete the challenge |
| `WARNING: Disney auth cookie was not found` | Login appeared to succeed but the auth cookie wasn't set | Manually re-seed in a TTY (§3); Disney may have invalidated the dedicated bot account |

After a Login Agent failure, owners should receive an SMS within ~10 min telling them manual re-seed is required. If you don't see that SMS, see §5.

### 2.3 Login Agent on cooldown

```
[bot] Login Agent on cooldown (last attempt 2026-XX-XXTXX:XX:XXZ).
[bot] Skipping Login Agent due to cooldown.
```

**Not an error by itself** — the bot retries at most every 9 minutes. Just wait one cycle. If you need to clear the cooldown manually:

```bash
# Edit bot_state.json in the Gist (or local file). Remove or zero out
# "last_login_agent_attempt_at". The next poll will retry recovery.
```

In practice, manually re-seeding (§3) is faster and resets the same condition.

### 2.4 Other miscellaneous failures

* `HTTP 428` — Akamai's crypto challenge, not a login problem. Do not re-seed first; see §2.5.
* `RuntimeError: Playwright is not installed` — `pip install -r requirements.txt && python3 -m playwright install chromium` inside the venv.
* `EPIPE` / Node driver crash when running the seeder by hand — usually a stale `SingletonLock` in the Chrome profile (see §4).

### 2.5 RUNBOOK: `HTTP 428` (Akamai crypto challenge)

```
[bot] Check failed for Space 220 Lounge: [monitor] Space 220 Lounge: HTTP 428 from availability API (Akamai challenge; see TROUBLESHOOTING.md 2.5)
```

**What it is.** Since 2026-11-11 Akamai answers the dining availability call with a crypto challenge (`{"sec-cp-challenge": "true", "provider": "crypto", "chlg_duration": 15, ...}`). A brand-new anonymous Chrome on another network gets the same 428, so it is not about this VPS, its IP or its login. `found via Playwright` and `HTTP 428 from availability API` come from the same in-page `fetch()`; there is no other dining path. Re-seeding does not clear it, and Harmony Barber Shop keeps working because `sa-api` is not behind the challenge.

**What clears it.** Akamai's own scripts solve the challenge in the browser: the 428 starts a proof-of-work (about 25 small `/_sec/verify` calls over 12 seconds), it ends with a call to `/_sec/cp_challenge/verify`, and the same `fetch()` then goes through. Only the `/dine-res/` pages carry the script that does this; opening the API URL or any other light page does not work.

**Why the attempt reloads the page first.** With the attempt on, PR #52 kept the signed-in restaurant page open while the challenge ran. On the 2 GB VPS the browser then grew from about 560 MB to 735, 1195 and 1512 MB in 10 to 13 seconds and never finished. That could not be reproduced away from the VPS with the same Playwright (1.59.0) and Chromium (build 1217), headed under Xvfb on 1 CPU: signed out, the challenge finished in 12 seconds with about 20 MB of growth, and it stayed flat with a quarter of a CPU, with a 20 times harder challenge, with a refused proof and with 50 challenges at once. What is left is the signed-in restaurant page itself (the app and the third-party scripts around it, with this profile) staying open longer than the 10 seconds a normal check takes. That is a conclusion by elimination, not something observed. So the attempt now reloads the restaurant page with everything blocked except Akamai's scripts, its challenge calls and the availability call. The app never starts on that page, and the browser used about 320 MB there.

**Why it is off by default.** The reload has not run on the VPS. Turn it on by hand and watch one poll (steps under "Turn the challenge attempt on").

**Limits the worker enforces on every poll** (all optional in `.env`):

| Setting | Default | Effect |
|---|---|---|
| `DISNEY_POLL_BUDGET_SECS` | 360 | Browser checks in one poll stop here. Restaurants not reached are reported as failed, not skipped silently. Time spent in login recovery is not counted. |
| `DISNEY_PAGE_BUDGET_SECS` | 120 | One restaurant's browser is stopped after this long, however it is stuck. |
| `DISNEY_BROWSER_MEM_LIMIT_MB` | 1000 | The browser is stopped when its memory (anonymous RAM plus swap, summed over all Chromium processes) passes this. |
| `DISNEY_AKAMAI_CHALLENGE_RETRIES` | 0 | `1` allows one challenge attempt per poll. |
| `DISNEY_AKAMAI_CHALLENGE_MEM_MB` | 700 | The attempt is abandoned when the browser is above this after the reload. |
| `DISNEY_AKAMAI_CHALLENGE_WAIT_MS` | 45000 | Longest wait for the challenge; it ends early when Akamai's verify call is seen. |
| `POLL_HARD_TIMEOUT_SECS` (`run_bot.sh`) | 780 | Last-resort kill of the whole poll process. |

"Stopped" means the renderers are killed so the stuck call fails and the browser closes normally; if it has not closed 5 seconds later, every browser process is killed and the profile's `Singleton*` lock files are removed. Each check logs `browser memory peak N MB, open Ns`.

#### Deploy and verify (attempt stays off)

Run as root on the VPS. There is no `pip` step, and do **not** run `playwright install`.

```bash
ssh -i ~/.ssh/disney_dining_vps root@107.170.35.91
cd /opt/disney-dining-bot

# 1. Pause the timer. The second command restarts it in 30 minutes even if this session dies.
systemctl stop disney-dining-bot.timer
systemd-run --on-active=30min /usr/bin/systemctl start disney-dining-bot.timer
while [ "$(systemctl show -p ActiveState --value disney-dining-bot.service)" = "activating" ]; do sleep 5; done

# 2. Deploy. The checkout is kept detached, so move it to main's tip directly.
git status -sb                       # no modified tracked files; untracked files are fine
git fetch origin main
git checkout --detach origin/main
git log -1 --oneline
grep -nE 'DISNEY_AKAMAI|DISNEY_PAGE_BUDGET|DISNEY_POLL_BUDGET|DISNEY_BROWSER_MEM' .env || echo "no overrides in .env"
. .venv/bin/activate
python3 -m py_compile monitor.py seed_disney_session.py disney_bot.py && bash -n run_bot.sh && echo compile-ok

# 3. Once: give the unit a start timeout. A oneshot unit has none, which is why a hung poll ran for 30 minutes.
mkdir -p /etc/systemd/system/disney-dining-bot.service.d
printf '[Service]\nTimeoutStartSec=840\n' > /etc/systemd/system/disney-dining-bot.service.d/10-timeout.conf
systemctl daemon-reload
systemctl show -p TimeoutStartUSec disney-dining-bot.service     # TimeoutStartUSec=14min

# 4. One poll without blocking the shell. Output is live.
systemctl start --no-block disney-dining-bot.service
journalctl -f -u disney-dining-bot.service       # Ctrl-C after "=== poll done ==="
#    No "poll done" after 8 minutes: systemctl kill -s SIGKILL disney-dining-bot.service, then roll back.

# 5. ALWAYS restart the timer, whatever happened above.
systemctl start disney-dining-bot.timer
systemctl is-active disney-dining-bot.timer                  # active
systemctl list-timers disney-dining-bot.timer --no-pager     # next run within 10 min
```

With the attempt off, step 4 should look like a poll on `a6f1360`: the same `HTTP 428` failures for dining, Harmony Barber Shop still checked, about 2 minutes in total, plus one `browser memory peak N MB, open Ns` line per check. Those peak numbers are the real memory cost on this box; keep them. `/_api/health` stays 503 until dining checks pass, so this step does not bring alerts back.

If step 2's `grep` shows `DISNEY_AKAMAI_CHALLENGE_RETRIES=1`, step 4 runs the challenge attempt; set it to `0` first if you only want to check the deploy.

#### Turn the challenge attempt on

The box needs 2 GB of RAM (the droplet was resized on 2026-11-12). Set these in `/opt/disney-dining-bot/.env`:

```
DISNEY_AKAMAI_CHALLENGE_RETRIES=1
DISNEY_AKAMAI_CHALLENGE_MEM_MB=700
```

Then repeat steps 1, 4 and 5. The first challenged restaurant should log, in this order:

```
[monitor] <name>: HTTP 428 Akamai challenge; reloading the page with only Akamai's scripts (browser at ~560 MB).
[monitor] <name>: waiting up to 45s for the challenge to finish (browser at N MB, challenge ceiling 700 MB).
[monitor] <name>: Akamai challenge finished in Ns (N proof rounds answered); availability API now returns HTTP 200.
```

Confirm from outside after a poll with no failed restaurant:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://magictablefinder.com/_api/health    # 200
curl -s https://magictablefinder.com/_api/health    # {"ok":true,"last_successful_poll_at":"...","age_minutes":<10 or less>}
```

| Log line | Meaning |
|---|---|
| `finished in Ns (...); availability API now returns HTTP 200` (or `404`) | Cleared. Later restaurants should show no Akamai lines. Health turns 200 after one poll with no failed restaurant. |
| `waiting up to 45s ... (browser at N MB` with N well under 560 | The reload worked: the app is gone from the page. |
| `finished in Ns (...); availability API now returns HTTP 428` | Akamai ran the challenge to the end and still refuses this browser. Waiting will not fix that; see "If it still does not clear". |
| `abandoned after Ns: the browser reached N MB (...; largest process: ...); N proof rounds answered` | Memory grew even without the app. Keep the whole line: the proof-round count says whether the challenge was running, and the largest process says where the memory went. |
| `abandoned after 45s: no verify call within 45s; 0 proof rounds answered` | The challenge never started on the reloaded page. Akamai's script did not load or did not react. |
| `abandoned after 45s: no verify call within 45s; N proof rounds answered` | The challenge was running but slow. Try `DISNEY_AKAMAI_CHALLENGE_WAIT_MS=75000` once. |
| `N of them not HTTP 200` | Akamai refused that many proof rounds. |
| `attempt abandoned: the reload failed (...)` | The reload did not finish in 30 seconds. That check fails; the next poll tries again. |
| `not attempting it because the response does not name Akamai's script path` | Akamai changed the 428 body. The code needs an update. |
| `this poll's one attempt is already used` | A later restaurant was challenged again after the one attempt. |
| `stopping the browser: it ...` | A hard limit fired. That check fails; the poll carries on. |
| `Disney auth required` | The login really expired. Re-seed (below). |

**If it still does not clear.** Set `DISNEY_AKAMAI_CHALLENGE_RETRIES=0` again; polls go back to the clean 2 minute run. Then this approach (the VPS's own browser solving the challenge) is finished, and the cheapest alternative is to stop asking Disney from the VPS for dining: run the dining check from a machine whose browser is not challenged this way, or use a paid availability feed. Neither is in this repo today.

**Optional: confirm the cause.** With the attempt off, add `DISNEY_AKAMAI_WARMUP_MS=25000` to `.env` for one poll. That keeps each signed-in restaurant page open for 25 seconds with no challenge running. If `browser memory peak` jumps far above 560 MB, or a check ends with `stopping the browser: it used N MB`, the page itself is what grows. Remove the line afterwards.

The first clean poll after the outage alerts on openings that appeared while the worker was blind and are still open. That is expected. Do not clear `open_slots.json`.

**Optional kernel cap.** The limits above are enforced by the worker itself. To have the kernel enforce one too, add `MemoryMax=`, `MemorySwapMax=` and `OOMPolicy=continue` to the drop-in from step 3 (needs cgroup v2, Ubuntu 22.04 or later). Set `MemoryMax` at least 250 MB above the largest `browser memory peak` seen in healthy polls; too low a value makes every check fail with `Page crashed`.

**Re-seed, only for `Disney auth required`.** Same shell, timer still paused:

```bash
pgrep -af 'chrom' || echo "no browser running"        # must say "no browser running"
mkdir -p /var/log/disney-dining-bot
SEED_LOG=/var/log/disney-dining-bot/seed-$(date -u +%Y%m%dT%H%M%SZ).log
DISNEY_HEADLESS=false xvfb-run -a timeout 600 python3 seed_disney_session.py </dev/null >"$SEED_LOG" 2>&1; echo "seed exit=$?"
tail -n 40 "$SEED_LOG"
```

Exit 0 with `SUCCESS` means the profile is ready (`skipping login` means it was already signed in; `DISNEY_SEED_FORCE_LOGIN=1` forces the login). Exit 1 means no auth cookie (MFA or CAPTCHA needs a TTY, see §3). Exit 124 means it timed out. A `Page crashed` there used to fail all four retries because the seeder kept using the dead tab; it now continues in a fresh one and logs `[seed] Renderer crashed while on '<url>'`. If you see that, capture `journalctl -k --since "2 hours ago" --no-pager | grep -iE 'out of memory|oom-kill|killed process' | tail -n 20` and `free -m`.

**Roll back.** To switch the attempt off, set `DISNEY_AKAMAI_CHALLENGE_RETRIES=0` in `.env` (or delete the line). With it off, the worker never reloads a page and behaves as it did at `86478dd` (PR #52). For the code, `git checkout --detach 86478dd` returns to PR #52 and `git checkout --detach a6f1360` to what ran before PR #51; then repeat steps 4 and 5. The timer never needs to stay stopped.

---

## 3. Manually re-seed the Disney session

This is the universal fix when the bot says "Disney auth required" or "Re-seed the VPS browser profile".

```bash
ssh -t -i ~/.ssh/disney_dining_vps root@107.170.35.91 \
  'cd /opt/disney-dining-bot && . .venv/bin/activate && \
   DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py'
```

The `-t` allocates a TTY so you can press Enter when login completes. The script:

1. Opens a virtual-display Chrome under xvfb.
2. Navigates to a known-working Disney restaurant page, then clicks Sign In.
3. Tries automated login if `DISNEY_LOGIN_EMAIL` / `DISNEY_LOGIN_PASSWORD` are set in `.env`.
4. If automation fails (MFA, captcha, selector drift), it waits for you to press Enter — meaning you'd need to interact with the headed browser, which over xvfb you can't see directly.

**If the seeder needs visible interaction** (MFA, captcha, manual login), you have two options:

* **Push credentials and let it auto-login** (works if your dedicated bot account has MFA disabled / device trusted):
  ```bash
  # On macOS, copy your DISNEY password to clipboard, then:
  pbpaste | python3 scripts/sync_disney_login_to_vps.py --password-stdin --run-seed-and-poll
  ```
* **Forward X over SSH so you can see the browser:**
  ```bash
  ssh -X -t -i ~/.ssh/disney_dining_vps root@107.170.35.91 \
    'cd /opt/disney-dining-bot && . .venv/bin/activate && \
     DISNEY_HEADLESS=false python3 seed_disney_session.py'
  # Note: no xvfb-run, and you need XQuartz on macOS.
  ```

**Verify success:**

```bash
ssh -i ~/.ssh/disney_dining_vps root@107.170.35.91 \
  'systemctl start disney-dining-bot.service; sleep 60; \
   journalctl -u disney-dining-bot.service -n 30 --no-pager --since "2 minutes ago"'
```

You want to see `=== poll done ===` with no `Check failed` lines.

---

## 4. Stale `SingletonLock` (manual seeder crashes immediately with EPIPE)

If running `seed_disney_session.py` from an SSH session crashes within seconds with a Node.js `EPIPE` traceback (no `[seed]` log lines), Chrome cannot acquire the profile because of a leftover lock from a previously-killed Chromium.

```bash
ssh -i ~/.ssh/disney_dining_vps root@107.170.35.91 \
  'rm -f /opt/disney-dining-bot/.browser-profile/SingletonLock \
         /opt/disney-dining-bot/.browser-profile/SingletonCookie \
         /opt/disney-dining-bot/.browser-profile/SingletonSocket'
```

Also make sure no rogue Chromium is still running:

```bash
ssh -i ~/.ssh/disney_dining_vps root@107.170.35.91 'pgrep -af chromium; pgrep -af xvfb-run'
# kill any leftover processes if found
```

Then retry §3.

---

## 5. Signal alerts when the bot needs attention

When the Login Agent fails, the worker sends a Signal message **to Craig only** (the admin, default owner). Jessica gets her own reservation alerts via Signal but does not receive operational alerts. Rate-limited to one alert per 6 hours.

The body looks like:

```
Disney Dining Bot: Disney login session failed after automatic recovery.
Manual re-seed required. On a machine with your SSH key:
ssh -i ~/.ssh/disney_dining_vps -t root@107.170.35.91 'cd /opt/disney-dining-bot && . .venv/bin/activate && DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py'
```

### How alerts are routed

`notify.py` is a channel dispatcher. Each `WATCH_USERS[*].phone` value carries a prefix:

- `signal:+15551234567` → POSTs to local `signal-cli` on the VPS
- `signal:<account-uuid>` → same, used when the recipient has Signal phone-number-discoverability disabled (Craig's case — his Signal account UUID is stored, not his phone number)
- `whatsapp:+15551234567` → Twilio WhatsApp (legacy / fallback only)
- `+15551234567` → Twilio SMS (legacy / fallback only)

The bot's Signal sender account is `+19852359090` (a Google Voice number, registered with Signal under display name "Magic Table Finder"). Set in `.env` as `SIGNAL_BOT_NUMBER`. Operational alerts route to whatever `_configured_owner_phones()` returns, which is *only the admin's phone* — admin is `default_owner_id()` (i.e. `craig`) unless overridden via `DISNEY_ALERT_ADMIN`.

### If you didn't get a Signal alert but the bot is clearly broken

* Check `journalctl` for `[notify] signal-cli exit ...` or `[notify] signal-cli timed out` — signal-cli on the VPS hit an issue. Check `signal-cli -a +19852359090 listAccounts` works.
* Check `journalctl` for `[bot] Recovery failed but no owner phones are configured for alerting.` — `WATCH_USERS` in `.env` is missing the admin's phone.
* Check `bot_state.json:last_session_manual_alert_at` — if it's within the last 6 hours, you're inside the rate-limit window. The bot still needs a re-seed; you just won't get another Signal alert yet. Clear that field in the Gist if you need a fresh test alert.
* If signal-cli fails with `Unregistered user`: the recipient's Signal account hides their phone number. Have them message the bot's Signal number first, then run `signal-cli -a +19852359090 receive` once on the VPS to learn their UUID, then store `signal:<uuid>` in `WATCH_USERS` instead of `signal:+phone`.

## 5a. UptimeRobot — the external watchdog

The in-bot Signal alert can only fire when the bot is alive enough to detect a failure. If the VPS itself is down or the systemd timer dies, that alert never sends. UptimeRobot covers that case.

- **Monitor:** HTTP GET `https://magictablefinder.com/_api/health` every 5 minutes.
- **Healthy:** returns `200 {"ok":true,"last_successful_poll_at":"...","age_minutes":N}` when the bot has polled within the last 30 minutes.
- **Unhealthy:** returns `503 {"ok":false,"reason":"..."}` when stale or no poll on record.
- **Alert contact:** email to `craig@sco.gs`. Make sure the email app on Craig's phone has push notifications enabled.

If you want to tune the staleness threshold, set `HEALTH_STALE_MINUTES` in Netlify env vars (default 30).

---

## 6. Operational invariants you must preserve

These are subtle and have caused outages before. Keep them in mind whenever editing `.env` or the systemd unit.

### 6.1 `DISNEY_HEADLESS=false` in `.env`

Akamai detects "true" headless Chromium (`--headless=new`) on `disneyworld.disney.go.com` and aborts the connection with `ERR_HTTP2_PROTOCOL_ERROR` before any page renders. Even though the systemd service has no display, we run Chromium **headed** under `xvfb-run -a` (a virtual display). This is what `DISNEY_HEADLESS=false` does.

If you set `DISNEY_HEADLESS=true`, every poll and every recovery attempt will fail at navigation. The recovery subprocess in `disney_bot.py` explicitly forces `DISNEY_HEADLESS=false` to mirror the worker; do not "fix" that override back to true.

### 6.2 Refresh endpoint is dead — do not rely on it

`https://auth.registerdisney.go.com/v4/client/TPR-WDW-LBJS.WEB-PROD/guest/refreshAuth` currently returns Akamai 403 ("This distribution is not configured to allow the HTTP request method that was used for this request"). The bot logs this body verbatim now, but does **not** treat it as fatal — `monitor.py:_bearer_from_token_state` and `auth.py:get_valid_token` fall back to the unrefreshed access token whenever it still has > 60 s of life.

Disney's web layer renews the cookie on its own as soon as Playwright navigates to a Disney page, so we don't actually need the refresh endpoint while a session is live. We only need a re-seed when the cookie genuinely expires.

If you see a refresh succeed in the logs (`[auth] Disney token refreshed and saved.`), the endpoint has come back. Great. The fallback still protects you when it goes away again.

### 6.3 Persistent profile dir

`DISNEY_BROWSER_PROFILE_DIR=/opt/disney-dining-bot/.browser-profile` must persist across worker runs and reboots. The Disney auth cookie lives there. If the directory is wiped, you must re-seed (§3).

The systemd service does *not* touch this directory on startup. Be careful with `chown` / cleanup commands inside the app dir.

### 6.4 Login Agent cooldown vs. poll interval

* systemd timer: every 10 min (`OnUnitActiveSec=10min`)
* Login Agent cooldown: 9 min

These are tuned so every poll *can* attempt recovery if needed. If you raise the cooldown above the timer interval, you reintroduce a guaranteed silent-failure window — don't do that without thinking.

### 6.5 SMS alert rate-limit

After a Login Agent failure SMS, the worker waits 6 hours before sending another. This lives in `bot_state.json` as `last_session_manual_alert_at`. If you actively want a fresh test alert, clear that field in the Gist or wait for the window.

---

## 7. Diagnostic command cheat sheet

```bash
# Quickest "is the bot alive?" check, runs from any browser:
#   https://magictablefinder.com/_api/health
# Returns {"ok":true,...} or {"ok":false,...}

# Tail live logs
journalctl -u disney-dining-bot.service -f

# Last 200 lines, all errors and recovery events
journalctl -u disney-dining-bot.service -n 200 --no-pager | \
  grep -iE '(Check failed|recovery|Login Agent|auth|cookie|HTTP2|seed|SUCCESS)'

# Full output of the most recent automated recovery attempt
cat /var/log/disney-dining-bot/last-recovery.log

# Signal: confirm the bot's account is registered and reachable
signal-cli -a +19852359090 listAccounts
signal-cli -a +19852359090 send -m "manual test" <recipient>

# Manually re-seed Disney session (the canonical fix for "auth required" errors)
cd /opt/disney-dining-bot && . .venv/bin/activate && \
  DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py

# Force one immediate poll (don't wait for the 10-min timer)
systemctl start disney-dining-bot.service
sleep 60
journalctl -u disney-dining-bot.service -n 50 --no-pager --since "2 minutes ago"

# Pause the bot before risky changes
systemctl stop disney-dining-bot.timer
# ... do work ...
systemctl start disney-dining-bot.timer

# Check next scheduled run
systemctl list-timers disney-dining-bot.timer --no-pager

# Verify .env (without leaking secrets)
grep -E '^(DISNEY_|TWILIO_FROM|GITHUB_GIST_ID|WATCH_USERS)=' /opt/disney-dining-bot/.env | \
  sed -E 's/(PASSWORD|TOKEN|AUTH_TOKEN|EMAIL)=.*/\1=***/'
```

---

## 8. Escalation path

If the runbook above doesn't restore the bot in 30 minutes:

1. **Confirm Disney's site itself is up** in a normal browser. Major Disney outages do happen — there's nothing to fix on our side.
2. **Check whether Disney's API contract changed.** Symptom: polls navigate fine but `[monitor] {restaurant}: HTTP NNN from availability API`. Inspect the URL the worker calls (`/dine-res/api/availability/...`) in a real browser's network tab; if the path or required headers changed, `monitor.py` needs updating.
3. **Check the dedicated Disney bot account itself.** Log in manually from any browser. If Disney has flagged the account or forced a password reset, no amount of re-seeding will help until you fix that account.
4. **Pause the timer** so the bot stops sending duplicate failure alerts while you investigate:
   ```bash
   systemctl stop disney-dining-bot.timer
   ```
   Restart it once you've fixed whatever broke.
