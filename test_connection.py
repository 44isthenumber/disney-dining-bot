"""
Step 0 validation — run this FIRST before starting the bot.

Checks:
  1. curl_cffi Chrome impersonation gets past Akamai (200 vs 403)
  2. Calendar-days response parses correctly
  3. Slot-availability endpoint returns data
  4. Token decode works (prints expiry)
  5. (Optional) Twilio SMS test if credentials are present

Usage:
    cd ~/CursorProjects/disney-dining-bot
    cp .env.template .env        # fill in your values
    python test_connection.py
"""

import json
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

FACILITY_ID = "19063652"
FACILITY_SLUG = "jaleo"
BASE = "https://disneyworld.disney.go.com/dine-res/api"
STABLE_CONV_ID = "d319e5ec-8c0e-4070-92d0-d62a271b6dfd"


def check_env() -> bool:
    required = ["DISNEY_SWID", "DISNEY_AKACD", "DISNEY_ABCK", "DISNEY_BM_SZ"]
    missing = [k for k in required if not os.environ.get(k, "").strip()]
    # Need either DISNEY_ACCESS_TOKEN or DISNEY_TOKEN_BLOB
    has_token = os.environ.get("DISNEY_ACCESS_TOKEN", "").strip() or os.environ.get("DISNEY_TOKEN_BLOB", "").strip()
    if not has_token:
        missing.append("DISNEY_ACCESS_TOKEN (or DISNEY_TOKEN_BLOB)")
    if missing:
        print(f"[FAIL] Missing .env keys: {', '.join(missing)}")
        print("       Copy .env.template → .env and fill in your browser cookie values.")
        return False
    print("[OK]   All required .env keys present.")
    return True


def check_token() -> str:
    """Decode + print token expiry without making any network calls."""
    from auth import get_valid_token, _jwt_exp
    import time
    try:
        token = get_valid_token()
        exp = _jwt_exp(token)
        remaining = int((exp - time.time()) / 60)
        print(f"[OK]   Token valid.  Expires in ~{remaining} min.  Prefix: {token[:30]}…")
        return token
    except Exception as e:
        print(f"[FAIL] Token error: {e}")
        sys.exit(1)


def check_calendar(token: str) -> bool:
    from curl_cffi import requests as cffi_requests
    cookies = {
        "SWID": os.environ["DISNEY_SWID"],
        "akacd_dineplan": os.environ["DISNEY_AKACD"],
        "_abck": os.environ["DISNEY_ABCK"],
        "bm_sz": os.environ["DISNEY_BM_SZ"],
    }
    headers = {
        "Authorization": f"BEARER {token}",
        "x-function-name": "getCalendarDays",
        "x-disney-internal-dine-vas-365": "true",
        "x-disney-internal-dine-vas-eks": "true",
        "x-conversation-id": STABLE_CONV_ID,
        "x-correlation-id": str(uuid.uuid4()),
        "referer": f"https://disneyworld.disney.go.com/dine-res/restaurant/{FACILITY_SLUG}",
        "accept": "application/json, text/plain, */*",
    }

    print(f"\n[...] GET calendar-days for facilityId={FACILITY_ID} …")
    resp = cffi_requests.get(
        f"{BASE}/calendar-days",
        params={"facilityId": FACILITY_ID, "entityType": "restaurant"},
        headers=headers,
        cookies=cookies,
        impersonate="chrome120",
        timeout=15,
    )
    print(f"      Status: {resp.status_code}  |  Body size: {len(resp.content)} bytes")

    if resp.status_code == 200:
        try:
            data = resp.json()
            print(f"      Response (truncated): {json.dumps(data)[:300]}")
            print("[OK]   Calendar-days endpoint works — curl_cffi is NOT blocked by Akamai.")
            return True
        except Exception:
            print(f"      Raw body: {resp.text[:300]}")
            print("[WARN] 200 but response is not JSON — inspect above.")
            return True
    elif resp.status_code == 403:
        print("[FAIL] 403 Forbidden — Akamai is blocking the request.")
        print("       Next step: switch to Playwright persistent browser profile.")
        print(f"       Response: {resp.text[:300]}")
        return False
    elif resp.status_code == 401:
        print("[FAIL] 401 Unauthorized — token may be expired or malformed.")
        print("       Grab a fresh DISNEY_TOKEN_BLOB from your browser and update .env.")
        return False
    else:
        print(f"[FAIL] Unexpected status {resp.status_code}")
        print(f"       Response: {resp.text[:500]}")
        return False


def check_slots(token: str) -> None:
    from curl_cffi import requests as cffi_requests
    cookies = {
        "SWID": os.environ["DISNEY_SWID"],
        "akacd_dineplan": os.environ["DISNEY_AKACD"],
        "_abck": os.environ["DISNEY_ABCK"],
        "bm_sz": os.environ["DISNEY_BM_SZ"],
    }
    headers = {
        "Authorization": f"BEARER {token}",
        "x-function-name": "getAvailability",  # correct function name for slot endpoint
        "x-disney-internal-dine-vas-365": "true",
        "x-disney-internal-dine-vas-eks": "true",
        "x-conversation-id": STABLE_CONV_ID,
        "x-correlation-id": str(uuid.uuid4()),
        "referer": f"https://disneyworld.disney.go.com/dine-res/restaurant/{FACILITY_SLUG}",
        "accept": "application/json, text/plain, */*",
    }

    print(f"\n[...] GET slot availability (party=2, Jun 1-7) …")
    resp = cffi_requests.get(
        f"{BASE}/availability/2/2026-06-01,2026-06-07",
        params={"facilityId": FACILITY_ID, "entityType": "restaurant"},
        headers=headers,
        cookies=cookies,
        impersonate="chrome120",
        timeout=20,
    )
    print(f"      Status: {resp.status_code}  |  Body size: {len(resp.content)} bytes")
    if resp.status_code == 200:
        try:
            data = resp.json()
            print(f"      Top-level keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
            print(f"      Response (truncated): {json.dumps(data)[:500]}")
            print("[OK]   Slot-availability endpoint works.")
        except Exception:
            print(f"      Raw: {resp.text[:500]}")
    else:
        print(f"[WARN] Status {resp.status_code}: {resp.text[:300]}")


def check_twilio() -> None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_ = os.environ.get("TWILIO_FROM", "")
    to = os.environ.get("TWILIO_TO", "")
    if not all([sid, token, from_, to]) or sid.startswith("AC" + "x"):
        print("\n[SKIP] Twilio credentials not configured — skipping SMS test.")
        return

    print("\n[...] Sending Twilio test SMS …")
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(
            body="Disney dining bot test message — if you got this, Twilio is working!",
            from_=from_,
            to=to,
        )
        print(f"[OK]   Test SMS sent.  SID: {msg.sid}")
    except Exception as e:
        print(f"[FAIL] Twilio error: {e}")


def main():
    print("=" * 60)
    print("  Disney Dining Bot — Connection Test")
    print("=" * 60)

    if not check_env():
        sys.exit(1)

    token = check_token()
    calendar_ok = check_calendar(token)

    if calendar_ok:
        check_slots(token)

    check_twilio()

    print("\n" + "=" * 60)
    if calendar_ok:
        print("All checks passed.  Run the bot with:")
        print("    python disney_bot.py --once    # single poll")
        print("    python disney_bot.py           # continuous monitor")
    else:
        print("Calendar check failed.  See notes above before running the bot.")
    print("=" * 60)


if __name__ == "__main__":
    main()
