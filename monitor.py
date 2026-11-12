"""
Two-stage Disney dining availability monitor.

Stage 1 (cheap, ~105 bytes): calendar-days — which dates have ANY opening.
Stage 2 (detailed, ~34 kB):  availability/{partySize}/{start},{end} — bookable slots.

Correct endpoint discovered from main.js bundle:
  GET /dine-res/api/availability/{partySize}/{startDate},{endDate}
       ?facilityId={facilityId}&entityType=restaurant
  X-Function-Name: getAvailability

Response shape:
  {"restaurants": {"2026-06-01": [<MealPeriod>, ...], ...}, "statusCode": 200}
  MealPeriod: {mealPeriodType, offersByAccessibility: [{offers: [{offerId, time, label}]}]}
"""

import base64
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

import auth  # noqa: E402

BASE = "https://disneyworld.disney.go.com/dine-res/api"
STABLE_CONV_ID = str(uuid.uuid4())
TOKEN_COOKIE_NAME = "TPR-WDW-LBJS.WEB-PROD.token"


def _max_bookable_date() -> date:
    """Disney opens the next 60th booking day at 6 AM Eastern."""
    tz = ZoneInfo(os.environ.get("DISNEY_BOOKING_TIMEZONE", "America/New_York"))
    now = datetime.now(tz)
    window_days = int(os.environ.get("DISNEY_BOOKING_WINDOW_DAYS", "60"))
    opening_hour = int(os.environ.get("DISNEY_BOOKING_OPEN_HOUR", "6"))
    if now.time() < datetime_time(opening_hour, 0):
        window_days -= 1
    return now.date() + timedelta(days=window_days)


def _filter_bookable_dates(dates: List[str], name: str) -> List[str]:
    max_date = _max_bookable_date()
    bookable = [d for d in dates if date.fromisoformat(d) <= max_date]
    skipped = len(dates) - len(bookable)
    if skipped:
        print(f"[monitor] {name}: skipping {skipped} date(s) outside Disney's current booking window.")
    return bookable


def _normalize_hhmm(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(value.upper(), fmt).strftime("%H:%M")
        except ValueError:
            pass
    return value


def _time_in_window(offer_time: str, time_from: Optional[str], time_to: Optional[str]) -> bool:
    offer_time = _normalize_hhmm(offer_time) or offer_time
    time_from = _normalize_hhmm(time_from)
    time_to = _normalize_hhmm(time_to)
    if time_from and offer_time < time_from:
        return False
    if time_to and offer_time > time_to:
        return False
    return True


@dataclass
class Slot:
    restaurant_name: str
    facility_id: str
    date: str        # "YYYY-MM-DD"
    time: str        # "HH:MM" 24-hr
    label: str       # "11:35 AM" — human-readable
    meal_period: str # "Lunch" / "Dinner"
    party_size: int
    offer_id: str    # opaque booking token
    slug: str = ""
    owner_id: str = ""
    watch_id: str = ""
    recipient_phone: str = ""
    booking_type: str = "dining"  # "dining" or "scheduled_activity" (Enchanting Extras)


class DisneyAuthRequired(RuntimeError):
    """Raised when the browser profile has no refreshable Disney login state."""


@dataclass
class DisneyTokenState:
    access_token: str = ""
    refresh_token: str = ""
    source: str = ""
    expires_at: int = 0
    error: str = ""


def _strip_bearer(value: str) -> str:
    value = (value or "").strip()
    if value.upper().startswith("BEARER "):
        return value[7:].strip()
    return value


def _token_exp(token: str) -> int:
    try:
        return auth._jwt_exp(_strip_bearer(token))
    except Exception:
        return 0


def _raw_cookie_blob(value: str) -> str:
    value = (value or "").strip()
    return value.split("=", 1)[1] if value[:3].count("=") else value


def _token_state_from_cookie_value(value: str) -> DisneyTokenState:
    """Extract access/refresh tokens from Disney's encoded token cookie."""
    raw = _raw_cookie_blob(value)
    if not raw:
        return DisneyTokenState(source="cookie", error="empty token cookie")

    try:
        data = auth._decode_token_blob(raw)
    except Exception as exc:
        # Keep a regex fallback for older/odd cookie blobs that decode to a string
        # containing a JWT but not a clean JSON object.
        try:
            padding = (4 - len(raw) % 4) % 4
            decoded = base64.b64decode(raw + "=" * padding).decode("latin-1")
            matches = re.findall(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", decoded)
            access = matches[0] if matches else ""
            return DisneyTokenState(
                access_token=access,
                source="cookie",
                expires_at=_token_exp(access),
                error="" if access else f"token cookie decode failed: {type(exc).__name__}",
            )
        except Exception:
            return DisneyTokenState(source="cookie", error=f"token cookie decode failed: {type(exc).__name__}")

    access = (
        data.get("access_token")
        or data.get("accessToken")
        or data.get("swid_token")
        or data.get("swidToken")
        or ""
    )
    refresh = (
        data.get("refresh_token")
        or data.get("refreshToken")
        or ""
    )
    return DisneyTokenState(
        access_token=_strip_bearer(access),
        refresh_token=refresh,
        source="cookie",
        expires_at=_token_exp(access),
        error="" if access else f"token cookie had no access token; keys={sorted(data.keys())}",
    )


def _token_state_from_saved_tokens() -> DisneyTokenState:
    try:
        tokens = auth.load_tokens()
    except Exception as exc:
        return DisneyTokenState(source="tokens.json", error=f"saved token load failed: {type(exc).__name__}")
    access = _strip_bearer(tokens.get("access_token", ""))
    return DisneyTokenState(
        access_token=access,
        refresh_token=tokens.get("refresh_token", ""),
        source="tokens.json",
        expires_at=_token_exp(access),
        error="" if access else "saved token had no access token",
    )


def _bearer_from_token_state(state: DisneyTokenState) -> str:
    """Return a BEARER token, refreshing and persisting when possible.

    If refresh fails but the existing access token still has > MIN_USABLE_TOKEN_SECS
    of life left, fall back to the unrefreshed token rather than killing the session.
    Disney's refresh endpoint has been intermittently rejecting our calls; the
    cookie itself is honored by the dining API for as long as the JWT is valid.
    """
    if not state.access_token:
        return ""

    remaining = state.expires_at - time.time() if state.expires_at else 0
    if remaining >= auth.REFRESH_AHEAD_SECS:
        return f"BEARER {state.access_token}"

    if state.refresh_token:
        print(f"[auth] Disney {state.source} token expires in {int(remaining)}s — refreshing.")
        try:
            refreshed = auth._do_refresh({
                "access_token": state.access_token,
                "refresh_token": state.refresh_token,
            })
            auth.save_tokens(refreshed)
            print("[auth] Disney token refreshed and saved.")
            return f"BEARER {_strip_bearer(refreshed['access_token'])}"
        except Exception as exc:
            if remaining > auth.MIN_USABLE_TOKEN_SECS:
                print(
                    f"[auth] Refresh failed for {state.source} "
                    f"({type(exc).__name__}: {exc}); "
                    f"using unrefreshed access token ({int(remaining)}s left)."
                )
                return f"BEARER {state.access_token}"
            raise

    if remaining > auth.MIN_USABLE_TOKEN_SECS:
        return f"BEARER {state.access_token}"

    return ""


def _get_token_from_chrome() -> str:
    """Extract live Disney access token from Chrome's cookie store."""
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name="disneyworld.disney.go.com")
        for c in cj:
            if c.name == TOKEN_COOKIE_NAME:
                token = _bearer_from_cookie_value(c.value)
                if token:
                    return token
    except Exception:
        pass
    fallback = _strip_bearer(os.environ.get("DISNEY_ACCESS_TOKEN", ""))
    return f"BEARER {fallback}" if fallback else ""


def _bearer_from_cookie_value(value: str) -> str:
    """Extract a Disney Bearer JWT from the encoded token cookie value."""
    return _bearer_from_token_state(_token_state_from_cookie_value(value))


def _run_js_in_disney_tab(js: str, timeout: int = 12) -> str:
    """Execute JS in Chrome's Disney tab via AppleScript."""
    script = f"""
tell application "Google Chrome"
    set disneyTab to missing value
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "disneyworld.disney.go.com" then
                set disneyTab to t
                exit repeat
            end if
        end repeat
        if disneyTab is not missing value then exit repeat
    end repeat
    if disneyTab is missing value then
        return "ERROR: no Disney tab open in Chrome"
    end if
    return execute disneyTab javascript {json.dumps(js)}
end tell
"""
    return subprocess.check_output(
        ["osascript", "-e", script], stderr=subprocess.PIPE, timeout=timeout
    ).decode().strip()


def _navigate_disney_tab(url: str) -> None:
    """Navigate Chrome's Disney tab to url."""
    script = f"""
tell application "Google Chrome"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "disneyworld.disney.go.com" then
                set URL of t to {json.dumps(url)}
                return "ok"
            end if
        end repeat
    end repeat
    return "ERROR: no Disney tab"
end tell
"""
    subprocess.check_output(["osascript", "-e", script], stderr=subprocess.PIPE, timeout=8)


def _cookies() -> dict:
    # Try to read live cookies from Chrome first (always fresh, no manual updates needed).
    # Falls back to .env values if Chrome cookies aren't available (CI / headless envs).
    try:
        import browser_cookie3
        cj_go = browser_cookie3.chrome(domain_name=".go.com")
        cj_dw = browser_cookie3.chrome(domain_name="disneyworld.disney.go.com")
        by_name = {c.name: c.value for c in list(cj_go) + list(cj_dw)}
        abck = by_name.get("_abck", "")
        bm_sz = by_name.get("bm_sz", "")
        akacd = by_name.get("akacd_dineplan", "")
        swid = by_name.get("SWID", os.environ.get("DISNEY_SWID", ""))
        if abck and bm_sz and akacd:
            return {"SWID": swid, "akacd_dineplan": akacd, "_abck": abck, "bm_sz": bm_sz}
    except Exception:
        pass
    return {
        "SWID": os.environ["DISNEY_SWID"],
        "akacd_dineplan": os.environ["DISNEY_AKACD"],
        "_abck": os.environ["DISNEY_ABCK"],
        "bm_sz": os.environ["DISNEY_BM_SZ"],
    }


def _headers(token: str, function_name: str, slug: str) -> dict:
    return {
        "Authorization": f"BEARER {token}",
        "x-function-name": function_name,
        "x-disney-internal-dine-vas-365": "true",
        "x-disney-internal-dine-vas-eks": "true",
        "x-conversation-id": STABLE_CONV_ID,
        "x-correlation-id": str(uuid.uuid4()),
        "referer": f"https://disneyworld.disney.go.com/dine-res/restaurant/{slug}",
        "accept": "application/json, text/plain, */*",
    }


def _get(url: str, params: dict, token: str, function_name: str, slug: str):
    from curl_cffi import requests as cffi_requests
    resp = cffi_requests.get(
        url,
        params=params,
        headers=_headers(token, function_name, slug),
        cookies=_cookies(),
        impersonate="chrome120",
        timeout=15,
    )
    if resp.status_code == 401:
        raise RuntimeError("Disney returned 401 — token likely expired.")
    if resp.status_code == 403:
        raise RuntimeError(
            "Disney returned 403 — Akamai may be blocking.  "
            "Consider switching to Playwright persistent profile."
        )
    resp.raise_for_status()
    return resp.json()


# ── Stage 1: calendar days ─────────────────────────────────────────────────

def get_available_calendar_days(facility_id: str, token: str, slug: str) -> set:
    """Return set of date strings ('YYYY-MM-DD') that have any availability."""
    data = _get(
        f"{BASE}/calendar-days",
        params={"facilityId": facility_id, "entityType": "restaurant"},
        token=token,
        function_name="getCalendarDays",
        slug=slug,
    )
    # Response: {"bookingDateRanges": {"startDate": "...", "endDate": "..."}, ...}
    # The green dots on the calendar are driven by this; if startDate/endDate is
    # returned, ALL dates in that range have at least some availability.
    if "bookingDateRanges" in data:
        ranges = data["bookingDateRanges"]
        # May be a single dict or a list of dicts
        if isinstance(ranges, dict):
            ranges = [ranges]
        available = set()
        for r in ranges:
            start = date.fromisoformat(r["startDate"])
            end = date.fromisoformat(r["endDate"])
            cur = start
            while cur <= end:
                available.add(cur.isoformat())
                cur += timedelta(days=1)
        return available
    # Fallback: list of date strings
    if isinstance(data, list):
        return {item.get("date") or item.get("calendarDate") for item in data if item}
    return set()


# ── Stage 2: slot details ──────────────────────────────────────────────────

def _expand_dates(
    dates: Optional[List[str]],
    date_start: Optional[str],
    date_end: Optional[str],
) -> List[str]:
    if dates:
        return sorted(dates)
    if date_start and date_end:
        start = date.fromisoformat(date_start)
        end = date.fromisoformat(date_end)
        result = []
        cur = start
        while cur <= end:
            result.append(cur.isoformat())
            cur += timedelta(days=1)
        return result
    return []


def get_slots(
    facility_id: str,
    token: str,
    slug: str,
    restaurant_name: str,
    dates: List[str],
    party_size: int,
    meal_periods: List[str],
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> List[Slot]:
    if not dates:
        return []

    start = min(dates)
    end = max(dates)
    target_dates = set(dates)
    target_meals = {m.upper() for m in meal_periods} if meal_periods else {"ALL"}

    data = _get(
        f"{BASE}/availability/{party_size}/{start},{end}",
        params={"facilityId": facility_id, "entityType": "restaurant"},
        token=token,
        function_name="getAvailability",
        slug=slug,
    )

    # Response: {"restaurants": {"2026-06-01": [<MealPeriod>, ...]}, "statusCode": 200}
    by_date = data.get("restaurants", {})
    slots: List[Slot] = []

    for entry_date, meal_period_list in by_date.items():
        if entry_date not in target_dates:
            continue
        for mp in meal_period_list:
            meal = (mp.get("mealPeriodType") or "UNKNOWN").upper()
            if "ALL" not in target_meals and meal not in target_meals:
                continue

            # Dig into offersByAccessibility → offers
            for access_group in mp.get("offersByAccessibility", []):
                for offer in access_group.get("offers", []):
                    offer_time = offer.get("time", "")[:5]  # "11:35:00" → "11:35"
                    label = offer.get("label", offer_time)
                    offer_id = offer.get("offerId", "")

                    if not _time_in_window(offer_time, time_from, time_to):
                        continue

                    slots.append(Slot(
                        restaurant_name=restaurant_name,
                        facility_id=facility_id,
                        slug=slug,
                        date=entry_date,
                        time=offer_time,
                        label=label,
                        meal_period=meal,
                        party_size=party_size,
                        offer_id=str(offer_id),
                    ))

    return slots


# ── Public API used by disney_bot.py ──────────────────────────────────────

def check_restaurant(restaurant: dict, token: str) -> List[Slot]:
    """
    Given a restaurant config dict (from config.yaml) and a valid Bearer token,
    return all matching open slots.
    """
    facility_id = restaurant["facility_id"]
    slug = restaurant.get("slug", facility_id)
    name = restaurant.get("name", facility_id)
    party_size = int(restaurant.get("party_size", 2))
    meal_periods = restaurant.get("meal_periods", ["ALL"])
    time_from = restaurant.get("time_from")
    time_to = restaurant.get("time_to")

    dates = _expand_dates(
        restaurant.get("dates"),
        restaurant.get("date_start"),
        restaurant.get("date_end"),
    )
    if not dates:
        print(f"[monitor] {name}: no dates configured, skipping.")
        return []

    # Stage 1: cheap calendar check
    available_days = get_available_calendar_days(facility_id, token, slug)
    target_dates = [d for d in dates if d in available_days]
    if not target_dates:
        print(f"[monitor] {name}: no availability on target dates (calendar check).")
        return []

    print(f"[monitor] {name}: {len(target_dates)} date(s) show availability — fetching slots …")

    # Stage 2: detailed slot check
    return get_slots(
        facility_id=facility_id,
        token=token,
        slug=slug,
        restaurant_name=name,
        dates=target_dates,
        party_size=party_size,
        meal_periods=meal_periods,
        time_from=time_from,
        time_to=time_to,
    )


# ── Playwright browser checks for VPS worker ───────────────────────────────

AKAMAI_CHALLENGE_STATUS = 428
# Akamai's in-page challenge script calls this once the proof-of-work is done.
_AKAMAI_VERIFY_PATH = "/_sec/cp_challenge/verify"
# Time kept back after the challenge wait for the re-fetch and a clean close.
_AKAMAI_CHALLENGE_RESERVE_SECS = 15

_GUARD_INTERVAL_SECS = 1.0
# After the guard kills the renderers, the caller gets this long to close the
# browser cleanly (so the profile is flushed) before everything is killed.
_GUARD_KILL_GRACE_SECS = 5.0

_poll_deadline: Optional[float] = None   # time.monotonic(); None outside a poll
_akamai_attempt_used = False

_AVAILABILITY_FETCH_JS = """async ({partySize, start, end, facilityId, token}) => {
  try {
    const resp = await fetch(`/dine-res/api/availability/${partySize}/${start},${end}?facilityId=${facilityId}&entityType=restaurant`,
      { headers: { 'Authorization': token, 'x-function-name': 'getAvailability',
                   'x-disney-internal-dine-vas-365': 'true', 'x-disney-internal-dine-vas-eks': 'true',
                   'accept': 'application/json, text/plain, */*' }});
    if (resp.status === 200) return { status: 200, data: await resp.json() };
    let body = '';
    if (resp.status === 428) { try { body = (await resp.text()).slice(0, 2000); } catch (e) {} }
    return { status: resp.status, data: null, body };
  } catch (e) {
    return { status: 0, error: String(e) };
  }
}"""


def _playwright_headless() -> bool:
    return os.environ.get("DISNEY_HEADLESS", "true").lower() not in {"0", "false", "no"}


def _playwright_profile_dir() -> str:
    return os.environ.get("DISNEY_BROWSER_PROFILE_DIR", ".browser-profile")


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        value = default
    return max(low, min(high, value))


def start_poll_budget() -> None:
    """Start one poll's wall-clock budget for browser checks and re-arm its single challenge attempt."""
    global _poll_deadline, _akamai_attempt_used
    _poll_deadline = time.monotonic() + _env_int("DISNEY_POLL_BUDGET_SECS", 360, 60, 900)
    _akamai_attempt_used = False


def extend_poll_budget(seconds: float) -> None:
    """Give back time the poll spent outside browser checks (login recovery has its own cap)."""
    global _poll_deadline
    if _poll_deadline is not None and seconds > 0:
        _poll_deadline += seconds


def _akamai_challenge_enabled() -> bool:
    """DISNEY_AKAMAI_CHALLENGE_RETRIES >= 1 allows one challenge attempt per poll. Off by default."""
    return _env_int("DISNEY_AKAMAI_CHALLENGE_RETRIES", 0, 0, 1) >= 1


def _akamai_challenge_wait_secs(result: dict) -> int:
    """Longest the challenge attempt waits for Akamai's verify call.

    The 428 body carries chlg_duration (15 today), the minimum the challenge
    runs; the wait ends as soon as the verify call is seen, so the cap only
    matters on a slow box.
    """
    override = (os.environ.get("DISNEY_AKAMAI_CHALLENGE_WAIT_MS") or "").strip()
    if override.isdigit():
        return max(5, min(90, int(override) // 1000))
    duration = 15
    try:
        body = json.loads((result or {}).get("body") or "{}")
        if isinstance(body, dict):
            duration = int(body.get("chlg_duration", duration))
    except (TypeError, ValueError):
        pass
    return max(5, min(60, duration)) + 30


def _browser_processes() -> List[Tuple[int, str]]:
    """(pid, cmdline) of every Chromium process this process launched. Empty without /proc."""
    try:
        pids = [int(entry) for entry in os.listdir("/proc") if entry.isdigit()]
    except OSError:
        return []
    children = {}
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as fh:
                stat = fh.read()
            ppid = int(stat[stat.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(pid)

    def cmdline(pid: int) -> str:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                return fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return ""

    found: List[Tuple[int, str]] = []
    # (pid, True once a browser's main process has been passed on the way down)
    stack = [(pid, False) for pid in children.get(os.getpid(), [])]
    while stack:
        pid, in_browser = stack.pop()
        cmd = cmdline(pid)
        if not in_browser and "--user-data-dir=" in cmd:
            in_browser = True
        if in_browser:
            found.append((pid, cmd))
        stack.extend((child, in_browser) for child in children.get(pid, []))
    return found


def _process_memory_kb(pid: int) -> int:
    """Anonymous memory a process holds in RAM plus what it has in swap, in kB."""
    total = 0
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith(("RssAnon:", "VmSwap:")):
                    total += int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return total


def _clear_profile_locks() -> None:
    """Remove the lock files a SIGKILLed Chromium leaves in its profile; a stale one can stop the next launch."""
    for leftover in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            os.unlink(os.path.join(_playwright_profile_dir(), leftover))
        except OSError:
            pass


class _BrowserGuard:
    """Wall-clock and memory limits for one browser launch.

    A sync Playwright call that hangs cannot be interrupted from Python. On a
    breach the guard kills the renderers, which makes the blocked call raise so
    the caller closes the context normally; if the caller has not finished a
    few seconds later it kills the rest of the browser too.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = time.monotonic()
        self.budget_secs = _env_int("DISNEY_PAGE_BUDGET_SECS", 120, 30, 300)
        self.deadline = self.started + self.budget_secs
        self._time_limit = f"ran past the {self.budget_secs}s page time limit"
        if _poll_deadline is not None and _poll_deadline < self.deadline:
            self.deadline = _poll_deadline
            self._time_limit = "was still open when this poll's time budget ran out"
        self.mem_limit_mb = _env_int("DISNEY_BROWSER_MEM_LIMIT_MB", 1000, 200, 8000)
        self.mem_mb: Optional[int] = None   # last sample; None until /proc shows the browser
        self.peak_mb = 0
        self.tripped = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="browser-guard", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def seconds_left(self) -> float:
        return self.deadline - time.monotonic()

    def check(self) -> bool:
        """Take one sample. Kills the renderers and returns True when a limit is broken."""
        procs = _browser_processes()
        if procs:
            self.mem_mb = sum(_process_memory_kb(pid) for pid, _cmd in procs) // 1024
            self.peak_mb = max(self.peak_mb, self.mem_mb)
        if self.seconds_left() <= 0:
            reason = self._time_limit
        elif self.mem_mb is not None and self.mem_mb > self.mem_limit_mb:
            reason = f"used {self.mem_mb} MB of memory (limit {self.mem_limit_mb} MB)"
        else:
            return False
        if self._stop.is_set():
            # The caller has closed this browser; anything in /proc now belongs to the next check.
            return False
        self.tripped = reason
        print(f"[monitor] {self.name}: stopping the browser: it {self.tripped}.", flush=True)
        self._kill(procs, renderers_only=True)
        return True

    @staticmethod
    def _kill(procs: List[Tuple[int, str]], renderers_only: bool) -> None:
        for pid, cmd in procs:
            if renderers_only and "--type=renderer" not in cmd:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def _run(self) -> None:
        while not self._stop.wait(_GUARD_INTERVAL_SECS):
            if self.check():
                if not self._stop.wait(_GUARD_KILL_GRACE_SECS):
                    self._kill(_browser_processes(), renderers_only=False)
                    _clear_profile_locks()
                return


@contextmanager
def _guarded_browser(playwright, name: str):
    """Launch the persistent profile under a _BrowserGuard. Yields (context, guard); always closes the context."""
    if _poll_deadline is not None and time.monotonic() >= _poll_deadline:
        raise RuntimeError(f"[monitor] {name}: not checked; this poll's browser time budget is used up.")
    guard = _BrowserGuard(name)
    guard.start()
    context = None
    try:
        context = playwright.chromium.launch_persistent_context(
            _playwright_profile_dir(),
            headless=_playwright_headless(),
            args=["--no-sandbox"],
        )
        yield context, guard
    except Exception as exc:
        if guard.tripped:
            raise RuntimeError(f"[monitor] {name}: browser stopped because it {guard.tripped}.") from exc
        raise
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            if not guard.tripped:
                raise
        finally:
            guard.stop()
            if guard.peak_mb:
                print(f"[monitor] {name}: browser memory peak {guard.peak_mb} MB, "
                      f"open {int(time.monotonic() - guard.started)}s.", flush=True)


def _token_from_playwright_context(context) -> str:
    cookies = context.cookies(["https://disneyworld.disney.go.com", "https://disney.go.com"])
    cookie_names = {cookie.get("name", "") for cookie in cookies}
    parse_errors = []
    for cookie in cookies:
        if cookie.get("name") == TOKEN_COOKIE_NAME:
            state = _token_state_from_cookie_value(cookie.get("value", ""))
            if state.error:
                parse_errors.append(state.error)
            try:
                token = _bearer_from_token_state(state)
            except Exception as exc:
                parse_errors.append(f"cookie refresh failed: {type(exc).__name__}")
                token = ""
            if token:
                return token

    saved_state = _token_state_from_saved_tokens()
    if saved_state.error:
        parse_errors.append(saved_state.error)
    try:
        token = _bearer_from_token_state(saved_state)
    except Exception as exc:
        parse_errors.append(f"saved token refresh failed: {type(exc).__name__}")
        token = ""
    if token:
        return token

    fallback = _strip_bearer(os.environ.get("DISNEY_ACCESS_TOKEN", ""))
    if fallback and _token_exp(fallback) > time.time() + 60:
        return f"BEARER {fallback}"

    has_cookie = TOKEN_COOKIE_NAME in cookie_names
    detail = "; ".join(parse_errors[:3]) if parse_errors else "no usable token source"
    raise DisneyAuthRequired(
        "Disney auth required: "
        f"{'token cookie present but not refreshable' if has_cookie else 'token cookie missing'}; "
        f"{detail}. Re-seed the VPS browser profile with seed_disney_session.py."
    )


def disney_session_seconds_left(context) -> int:
    """Seconds of life left on the profile's Disney access token; 0 when absent or unreadable."""
    try:
        cookies = context.cookies(["https://disneyworld.disney.go.com", "https://disney.go.com"])
        remaining = 0
        for cookie in cookies or []:
            if cookie.get("name") != TOKEN_COOKIE_NAME:
                continue
            state = _token_state_from_cookie_value(cookie.get("value", ""))
            if state.access_token and state.expires_at:
                candidate = int(state.expires_at - time.time())
                if candidate > remaining:
                    remaining = candidate
        return max(0, remaining)
    except Exception:
        return 0


def _attempt_akamai_challenge(page, guard, result: dict, refetch, name: str) -> dict:
    """One bounded attempt per poll at Akamai's crypto challenge (HTTP 428). Off by default.

    The 428 has already started the challenge inside this page. Stay on the
    page, with no reload and no second tab, until Akamai's verify call
    returns, then fetch once more. Gives up without re-fetching when the wait
    cap, the page's time budget or the challenge memory ceiling is reached.
    """
    global _akamai_attempt_used
    if result.get("status") != AKAMAI_CHALLENGE_STATUS or not _akamai_challenge_enabled():
        return result
    if _akamai_attempt_used:
        print(f"[monitor] {name}: HTTP 428 Akamai challenge; this poll's one attempt is already used.", flush=True)
        return result
    _akamai_attempt_used = True

    mem_limit = _env_int("DISNEY_AKAMAI_CHALLENGE_MEM_MB", 500, 100, 8000)
    wait_cap = min(_akamai_challenge_wait_secs(result), int(guard.seconds_left()) - _AKAMAI_CHALLENGE_RESERVE_SECS)
    if guard.mem_mb is None:
        print(f"[monitor] {name}: HTTP 428 Akamai challenge; not attempting it because browser memory cannot be measured here.", flush=True)
        return result
    if guard.mem_mb > mem_limit:
        print(f"[monitor] {name}: HTTP 428 Akamai challenge; not attempting it because the browser is already at "
              f"{guard.mem_mb} MB (challenge ceiling {mem_limit} MB).", flush=True)
        return result
    if wait_cap < 5:
        print(f"[monitor] {name}: HTTP 428 Akamai challenge; not attempting it because the page's time budget is nearly used.", flush=True)
        return result

    verify_statuses: List[int] = []

    def on_response(response) -> None:
        try:
            if _AKAMAI_VERIFY_PATH in response.url:
                verify_statuses.append(response.status)
        except Exception:
            pass

    print(f"[monitor] {name}: HTTP 428 Akamai challenge; waiting up to {wait_cap}s on this page for it to finish "
          f"(browser at {guard.mem_mb} MB, challenge ceiling {mem_limit} MB).", flush=True)
    started = time.monotonic()
    gave_up = f"no verify call within {wait_cap}s"
    page.on("response", on_response)
    try:
        while time.monotonic() - started < wait_cap:
            page.wait_for_timeout(1000)
            if verify_statuses:
                break
            if guard.mem_mb > mem_limit:
                gave_up = f"the browser reached {guard.mem_mb} MB (challenge ceiling {mem_limit} MB)"
                break
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    waited = int(time.monotonic() - started)
    if not verify_statuses:
        print(f"[monitor] {name}: Akamai challenge attempt abandoned after {waited}s: {gave_up}.", flush=True)
        return result
    if verify_statuses[-1] != 200:
        print(f"[monitor] {name}: Akamai challenge verify call returned HTTP {verify_statuses[-1]} after {waited}s; not re-fetching.", flush=True)
        return result
    page.wait_for_timeout(1000)
    result = refetch()
    print(f"[monitor] {name}: Akamai challenge finished in {waited}s; availability API now returns HTTP {result.get('status')}.", flush=True)
    return result


def _parse_availability_response(
    *,
    data: dict,
    facility_id: str,
    slug: str,
    restaurant_name: str,
    dates: List[str],
    party_size: int,
    meal_periods: List[str],
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> List[Slot]:
    target_dates = set(dates)
    target_meals = {m.upper() for m in meal_periods} if meal_periods else {"ALL"}
    slots: List[Slot] = []
    for entry_date, meal_period_list in data.get("restaurants", {}).items():
        if entry_date not in target_dates:
            continue
        for mp in meal_period_list:
            meal = (mp.get("mealPeriodType") or "UNKNOWN").upper()
            if "ALL" not in target_meals and meal not in target_meals:
                continue
            for access_group in mp.get("offersByAccessibility", []):
                for offer in access_group.get("offers", []):
                    offer_time = offer.get("time", "")[:5]
                    if not _time_in_window(offer_time, time_from, time_to):
                        continue
                    slots.append(Slot(
                        restaurant_name=restaurant_name,
                        facility_id=facility_id,
                        date=entry_date,
                        time=offer_time,
                        label=offer.get("label", offer_time),
                        meal_period=meal,
                        party_size=party_size,
                        offer_id=str(offer.get("offerId", "")),
                        slug=slug,
                    ))
    return slots


def check_slots_via_playwright(restaurant: dict) -> List[Slot]:
    """
    Fetch availability from a persistent Playwright browser profile.

    This is the production path for the self-hosted monitor: it runs on a VPS
    and keeps its own browser profile, so the user's desktop Chrome is not part
    of the polling loop.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python3 -m playwright install chromium") from exc

    facility_id = restaurant["facility_id"]
    slug = restaurant.get("slug", facility_id)
    name = restaurant.get("name", facility_id)
    party_size = int(restaurant.get("party_size", 2))
    meal_periods = restaurant.get("meal_periods", ["ALL"])
    time_from = restaurant.get("time_from")
    time_to = restaurant.get("time_to")
    dates = _expand_dates(restaurant.get("dates"), restaurant.get("date_start"), restaurant.get("date_end"))
    if not dates:
        print(f"[monitor] {name}: no dates configured, skipping.")
        return []
    dates = _filter_bookable_dates(dates, name)
    if not dates:
        print(f"[monitor] {name}: no configured dates are bookable yet.")
        return []

    start, end = min(dates), max(dates)
    url = f"https://disneyworld.disney.go.com/dine-res/restaurant/{slug}"
    with sync_playwright() as p:
        with _guarded_browser(p, name) as (context, guard):
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(int(os.environ.get("DISNEY_AKAMAI_WARMUP_MS", "8000")))
            token = _token_from_playwright_context(context)
            fetch_args = {
                "partySize": party_size,
                "start": start,
                "end": end,
                "facilityId": facility_id,
                "token": token,
            }
            result = page.evaluate(_AVAILABILITY_FETCH_JS, fetch_args)
            result = _attempt_akamai_challenge(
                page, guard, result, lambda: page.evaluate(_AVAILABILITY_FETCH_JS, fetch_args), name,
            )

    if result.get("status") == 404:
        print(f"[monitor] {name}: no availability returned by Disney.")
        return []
    if result.get("status") != 200:
        status = result.get("status")
        hint = " (Akamai challenge; see TROUBLESHOOTING.md 2.5)" if status == AKAMAI_CHALLENGE_STATUS else ""
        raise RuntimeError(f"[monitor] {name}: HTTP {status} from availability API{hint} {result.get('error', '')}")
    slots = _parse_availability_response(
        data=result.get("data") or {},
        facility_id=facility_id,
        slug=slug,
        restaurant_name=name,
        dates=dates,
        party_size=party_size,
        meal_periods=meal_periods,
        time_from=time_from,
        time_to=time_to,
    )
    print(f"[monitor] {name}: {len(slots)} slot(s) found via Playwright.")
    return slots


def get_calendar_days_via_playwright(facility_id: str, slug: str) -> List[str]:
    """Fetch calendar availability using the same VPS Playwright browser profile."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python3 -m playwright install chromium") from exc

    url = f"https://disneyworld.disney.go.com/dine-res/restaurant/{slug}"
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            _playwright_profile_dir(),
            headless=_playwright_headless(),
            args=["--no-sandbox"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(int(os.environ.get("DISNEY_AKAMAI_WARMUP_MS", "8000")))
            token = _token_from_playwright_context(context)
            result = page.evaluate(
                """async ({facilityId, token}) => {
                  try {
                    const resp = await fetch(`/dine-res/api/calendar-days?facilityId=${facilityId}&entityType=restaurant`, {
                      headers: {
                        'Authorization': token,
                        'x-function-name': 'getCalendarDays',
                        'x-disney-internal-dine-vas-365': 'true',
                        'x-disney-internal-dine-vas-eks': 'true',
                        'accept': 'application/json, text/plain, */*',
                      }
                    });
                    return { status: resp.status, data: resp.status === 200 ? await resp.json() : null };
                  } catch (e) {
                    return { status: 0, error: String(e) };
                  }
                }""",
                {"facilityId": facility_id, "token": token},
            )
        finally:
            context.close()

    if result.get("status") != 200:
        raise RuntimeError(f"HTTP {result.get('status')} {result.get('error', '')}")
    data = result.get("data") or {}
    ranges = data.get("bookingDateRanges")
    if not ranges:
        return []
    if isinstance(ranges, dict):
        ranges = [ranges]
    available = set()
    for item in ranges:
        start = date.fromisoformat(item["startDate"])
        end = date.fromisoformat(item["endDate"])
        cur = start
        while cur <= end:
            available.add(cur.isoformat())
            cur += timedelta(days=1)
    return sorted(available)


# ── Scheduled activities ("Enchanting Extras", e.g. Harmony Barber Shop) ──
#
# These experiences are not in the dine-res API. They book through Disney's
# Scheduled Activity system on the same origin:
#   GET /sa-api/api/v1/experience/details/{slug}/
#       → bookableStartDate/bookableEndDate, product.schedules, availableDaysDateRange
#   GET /sa-api/api/v1/experience/offers/{productId}
#       ?entityType=activity-product&startDate=…&endDate=…&{ageGroup}=N
#       → bookableExperience.availableOffers.offers: {date: [offer, …]}
# Date windows must span at most availableDaysDateRange (9) days per request.
# sa-api authenticates via browser cookies — no bearer token is needed.

SA_PAGE_BASE = "https://disneyworld.disney.go.com/enchanting-extras-collection"
SA_API_BASE = "/sa-api/api/v1/experience"

_SA_FETCH_JS = """async (url) => {
  try {
    const resp = await fetch(url, { headers: {
      'accept': 'application/json, text/plain, */*',
      'skip-intercept': 'true',
    }});
    return { status: resp.status, data: resp.status === 200 ? await resp.json() : null };
  } catch (e) {
    return { status: 0, error: String(e) };
  }
}"""


def _sa_page_url(slug: str) -> str:
    return f"{SA_PAGE_BASE}/{slug}/"


def _sa_date_windows(dates: List[str], max_days: int = 9) -> List[tuple]:
    """Pack ISO dates into (start, end) windows spanning at most max_days days."""
    windows: List[tuple] = []
    remaining = sorted(set(dates))
    max_days = max(1, max_days)
    while remaining:
        start = date.fromisoformat(remaining[0])
        limit = (start + timedelta(days=max_days - 1)).isoformat()
        chunk = [d for d in remaining if d <= limit]
        windows.append((chunk[0], chunk[-1]))
        remaining = [d for d in remaining if d > limit]
    return windows


def _sa_scheduled_dates(details_result: dict, dates: List[str], name: str) -> tuple:
    """Clamp requested dates using the sa-api details response.

    Returns (dates bookable per Disney, request window size in days).
    """
    status = details_result.get("status")
    if status == 401:
        raise RuntimeError(f"[monitor] {name}: Disney returned 401 from sa-api details — session likely expired")
    if status != 200:
        raise RuntimeError(f"[monitor] {name}: HTTP {status} from sa-api details {details_result.get('error', '')}")
    data = details_result.get("data") or {}
    start = data.get("bookableStartDate") or ""
    end = data.get("bookableEndDate") or ""
    kept = [d for d in dates if (not start or d >= start) and (not end or d <= end)]
    product = ((data.get("bookableExperience") or {}).get("product")) or {}
    schedules = product.get("schedules") or []
    scheduled = {s.get("date") for s in schedules if (s.get("status") or "").upper() == "SCHEDULED"}
    if scheduled:
        kept = [d for d in kept if d in scheduled]
    try:
        window = int(product.get("availableDaysDateRange") or 9)
    except (TypeError, ValueError):
        window = 9
    return kept, max(1, min(window, 9))


def _parse_sa_offers_response(
    *,
    data: dict,
    facility_id: str,
    slug: str,
    restaurant_name: str,
    dates: List[str],
    party_size: int,
    meal_periods: List[str],
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> List[Slot]:
    target_dates = set(dates)
    target_meals = {m.upper() for m in meal_periods} if meal_periods else {"ALL"}
    slots: List[Slot] = []
    offers_by_date = (
        ((data or {}).get("bookableExperience") or {}).get("availableOffers") or {}
    ).get("offers") or {}
    for entry_date, offer_list in offers_by_date.items():
        if entry_date not in target_dates:
            continue
        for offer in offer_list or []:
            if (offer.get("status") or "").upper() == "UNAVAILABLE":
                continue
            start_time = offer.get("startTime") or ""
            if not start_time:
                continue
            offer_time = start_time[:5]
            if not _time_in_window(offer_time, time_from, time_to):
                continue
            meal = (offer.get("timePeriod") or "UNKNOWN").upper()
            if "ALL" not in target_meals and meal not in target_meals:
                continue
            try:
                label = datetime.strptime(offer_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
            except ValueError:
                label = offer_time
            slots.append(Slot(
                restaurant_name=restaurant_name,
                facility_id=facility_id,
                date=entry_date,
                time=offer_time,
                label=label,
                meal_period=meal,
                party_size=party_size,
                offer_id=str(offer.get("priceId") or ""),
                slug=slug,
                booking_type="scheduled_activity",
            ))
    return slots


def _sa_raise_for_offers_status(result: dict, name: str) -> None:
    status = result.get("status")
    if status in (200, 404):
        return
    if status == 401:
        raise RuntimeError(f"[monitor] {name}: Disney returned 401 from sa-api offers — session likely expired")
    raise RuntimeError(f"[monitor] {name}: HTTP {status} from sa-api offers {result.get('error', '')}")


def check_scheduled_activity_slots_via_playwright(restaurant: dict) -> List[Slot]:
    """Availability check for scheduled activities via the persistent profile."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python3 -m playwright install chromium") from exc

    facility_id = restaurant["facility_id"]
    slug = restaurant.get("slug", facility_id)
    name = restaurant.get("name", facility_id)
    party_size = int(restaurant.get("party_size", 2))
    meal_periods = restaurant.get("meal_periods", ["ALL"])
    time_from = restaurant.get("time_from")
    time_to = restaurant.get("time_to")
    age_param = restaurant.get("age_param") or "adult"
    dates = _expand_dates(restaurant.get("dates"), restaurant.get("date_start"), restaurant.get("date_end"))
    if not dates:
        print(f"[monitor] {name}: no dates configured, skipping.")
        return []
    dates = _filter_bookable_dates(dates, name)
    if not dates:
        print(f"[monitor] {name}: no configured dates are bookable yet.")
        return []

    slots: List[Slot] = []
    with sync_playwright() as p:
        with _guarded_browser(p, name) as (context, _guard):
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(_sa_page_url(slug), wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(int(os.environ.get("DISNEY_AKAMAI_WARMUP_MS", "8000")))
            details = page.evaluate(_SA_FETCH_JS, f"{SA_API_BASE}/details/{slug}/")
            dates, window_days = _sa_scheduled_dates(details, dates, name)
            if not dates:
                print(f"[monitor] {name}: no requested dates inside Disney's bookable window.")
                return []
            for start, end in _sa_date_windows(dates, window_days):
                offers_url = (
                    f"{SA_API_BASE}/offers/{facility_id}?entityType=activity-product"
                    f"&startDate={start}&endDate={end}&{age_param}={party_size}"
                )
                result = page.evaluate(_SA_FETCH_JS, offers_url)
                _sa_raise_for_offers_status(result, name)
                if result.get("status") == 404:
                    continue
                slots.extend(_parse_sa_offers_response(
                    data=result.get("data") or {},
                    facility_id=facility_id,
                    slug=slug,
                    restaurant_name=name,
                    dates=dates,
                    party_size=party_size,
                    meal_periods=meal_periods,
                    time_from=time_from,
                    time_to=time_to,
                ))
                page.wait_for_timeout(800)

    print(f"[monitor] {name}: {len(slots)} slot(s) found via scheduled-activity API.")
    return slots


def get_scheduled_activity_calendar_days_via_playwright(
    facility_id: str,
    slug: str,
    party_size: int = 2,
    age_param: str = "adult",
) -> List[str]:
    """Dates with at least one bookable offer across the full bookable range.

    Sweeps the offers endpoint so the calendar cache reflects true
    availability (the SPA renders cached dates as "go book now"), not just
    operating days.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python3 -m playwright install chromium") from exc

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            _playwright_profile_dir(),
            headless=_playwright_headless(),
            args=["--no-sandbox"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(_sa_page_url(slug), wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(int(os.environ.get("DISNEY_AKAMAI_WARMUP_MS", "8000")))
            details = page.evaluate(_SA_FETCH_JS, f"{SA_API_BASE}/details/{slug}/")
            status = details.get("status")
            if status != 200:
                raise RuntimeError(f"HTTP {status} from sa-api details {details.get('error', '')}")
            data = details.get("data") or {}
            start = data.get("bookableStartDate")
            end = data.get("bookableEndDate")
            if not start or not end:
                return []
            all_dates = []
            cur = date.fromisoformat(start)
            last = date.fromisoformat(end)
            while cur <= last:
                all_dates.append(cur.isoformat())
                cur += timedelta(days=1)
            all_dates, window_days = _sa_scheduled_dates(details, all_dates, slug)
            available = set()
            for win_start, win_end in _sa_date_windows(all_dates, window_days):
                offers_url = (
                    f"{SA_API_BASE}/offers/{facility_id}?entityType=activity-product"
                    f"&startDate={win_start}&endDate={win_end}&{age_param}={party_size}"
                )
                result = page.evaluate(_SA_FETCH_JS, offers_url)
                if result.get("status") != 200:
                    continue
                offers_by_date = (
                    ((result.get("data") or {}).get("bookableExperience") or {}).get("availableOffers") or {}
                ).get("offers") or {}
                for entry_date, offer_list in offers_by_date.items():
                    if any((o.get("startTime") and (o.get("status") or "").upper() != "UNAVAILABLE") for o in offer_list or []):
                        available.add(entry_date)
                page.wait_for_timeout(800)
        finally:
            context.close()
    return sorted(available)


def check_slots_for_restaurant(restaurant: dict) -> List[Slot]:
    if (restaurant.get("booking_type") or "").lower() == "scheduled_activity":
        # Scheduled activities are Playwright-only; there is no dine-res
        # token path or AppleScript equivalent for sa-api.
        return check_scheduled_activity_slots_via_playwright(restaurant)
    mode = os.environ.get("DISNEY_BROWSER_MODE", "playwright").lower()
    if mode in {"applescript", "chrome"}:
        return check_slots_via_chrome(restaurant)
    if mode in {"direct", "http"}:
        token = os.environ.get("DISNEY_ACCESS_TOKEN", "")
        if not token:
            raise RuntimeError("DISNEY_ACCESS_TOKEN is required for direct HTTP mode")
        return check_restaurant(restaurant, token)
    return check_slots_via_playwright(restaurant)


# ── Chrome-based slot check (Akamai-proof) ────────────────────────────────

def check_slots_via_chrome(restaurant: dict) -> List[Slot]:
    """
    Navigate Chrome to the restaurant page, then fetch availability slots.
    Bypasses Akamai by running inside the real browser session.
    Raises RuntimeError if Chrome is unavailable or no Disney tab is open.
    """
    facility_id = restaurant["facility_id"]
    slug = restaurant.get("slug", facility_id)
    name = restaurant.get("name", facility_id)
    party_size = int(restaurant.get("party_size", 2))
    meal_periods = restaurant.get("meal_periods", ["ALL"])
    time_from = restaurant.get("time_from")
    time_to = restaurant.get("time_to")

    dates = _expand_dates(
        restaurant.get("dates"),
        restaurant.get("date_start"),
        restaurant.get("date_end"),
    )
    if not dates:
        print(f"[monitor] {name}: no dates configured, skipping.")
        return []

    token = _get_token_from_chrome()
    start, end = min(dates), max(dates)
    target_dates = set(dates)
    target_meals = {m.upper() for m in meal_periods} if meal_periods else {"ALL"}

    # Navigate to restaurant page so Akamai session is fresh.
    url = f"https://disneyworld.disney.go.com/dine-res/restaurant/{slug}"
    _navigate_disney_tab(url)
    time.sleep(6)

    fire_js = f"""
window._slotsResult = null;
(async function() {{
  const tok = {json.dumps(token)};
  try {{
    const resp = await fetch(
      '/dine-res/api/availability/{party_size}/{start},{end}?facilityId={facility_id}&entityType=restaurant',
      {{ headers: {{
          'Authorization': tok,
          'x-function-name': 'getAvailability',
          'x-disney-internal-dine-vas-365': 'true',
          'x-disney-internal-dine-vas-eks': 'true',
          'accept': 'application/json, text/plain, */*',
      }} }}
    );
    window._slotsResult = JSON.stringify({{
      status: resp.status,
      data: resp.status === 200 ? await resp.json() : null,
    }});
  }} catch(e) {{
    window._slotsResult = JSON.stringify({{status: 0, error: String(e)}});
  }}
}})();
'fired'
"""
    out = _run_js_in_disney_tab(fire_js, timeout=12)
    if out.startswith("ERROR"):
        raise RuntimeError(out)

    # Poll for result.
    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(3)
        raw = _run_js_in_disney_tab("String(window._slotsResult)", timeout=8)
        if raw and raw not in ("null", "undefined"):
            break
    else:
        raise RuntimeError(f"[monitor] {name}: timed out waiting for slot fetch")

    result = json.loads(raw)
    if result["status"] != 200:
        raise RuntimeError(f"[monitor] {name}: HTTP {result['status']} from availability API")

    by_date = result["data"].get("restaurants", {})
    slots: List[Slot] = []

    for entry_date, meal_period_list in by_date.items():
        if entry_date not in target_dates:
            continue
        for mp in meal_period_list:
            meal = (mp.get("mealPeriodType") or "UNKNOWN").upper()
            if "ALL" not in target_meals and meal not in target_meals:
                continue
            for access_group in mp.get("offersByAccessibility", []):
                for offer in access_group.get("offers", []):
                    offer_time = offer.get("time", "")[:5]
                    label = offer.get("label", offer_time)
                    offer_id = offer.get("offerId", "")
                    if not _time_in_window(offer_time, time_from, time_to):
                        continue
                    slots.append(Slot(
                        restaurant_name=name,
                        facility_id=facility_id,
                        date=entry_date,
                        time=offer_time,
                        label=label,
                        meal_period=meal,
                        party_size=party_size,
                        offer_id=str(offer_id),
                    ))

    print(f"[monitor] {name}: {len(slots)} slot(s) found via Chrome.")
    return slots
