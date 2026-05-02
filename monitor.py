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
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BASE = "https://disneyworld.disney.go.com/dine-res/api"
STABLE_CONV_ID = str(uuid.uuid4())


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


def _get_token_from_chrome() -> str:
    """Extract live Disney access token from Chrome's cookie store."""
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name="disneyworld.disney.go.com")
        for c in cj:
            if c.name == "TPR-WDW-LBJS.WEB-PROD.token":
                raw = c.value.split("=", 1)[1] if c.value[:3].count("=") else c.value
                padding = (4 - len(raw) % 4) % 4
                decoded = base64.b64decode(raw + "=" * padding).decode("latin-1")
                for jwt in re.findall(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", decoded):
                    try:
                        payload = json.loads(base64.b64decode(jwt.split(".")[1] + "=="))
                        if 0 < payload.get("exp", 0) - time.time() < 86400:
                            return f"BEARER {jwt}"
                    except Exception:
                        pass
    except Exception:
        pass
    return f"BEARER {os.environ.get('DISNEY_ACCESS_TOKEN', '')}"


def _bearer_from_cookie_value(value: str) -> str:
    """Extract a Disney Bearer JWT from the encoded token cookie value."""
    raw = value.split("=", 1)[1] if value[:3].count("=") else value
    padding = (4 - len(raw) % 4) % 4
    decoded = base64.b64decode(raw + "=" * padding).decode("latin-1")
    for jwt in re.findall(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", decoded):
        try:
            payload = json.loads(base64.b64decode(jwt.split(".")[1] + "=="))
            if 0 < payload.get("exp", 0) - time.time() < 86400:
                return f"BEARER {jwt}"
        except Exception:
            pass
    return ""


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

def _playwright_headless() -> bool:
    return os.environ.get("DISNEY_HEADLESS", "true").lower() not in {"0", "false", "no"}


def _playwright_profile_dir() -> str:
    return os.environ.get("DISNEY_BROWSER_PROFILE_DIR", ".browser-profile")


def _token_from_playwright_context(context) -> str:
    cookies = context.cookies(["https://disneyworld.disney.go.com", "https://disney.go.com"])
    for cookie in cookies:
        if cookie.get("name") == "TPR-WDW-LBJS.WEB-PROD.token":
            token = _bearer_from_cookie_value(cookie.get("value", ""))
            if token:
                return token
    fallback = os.environ.get("DISNEY_ACCESS_TOKEN", "")
    return f"BEARER {fallback}" if fallback else ""


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
            if not token:
                raise RuntimeError("No Disney auth token found in Playwright profile. Log in on the VPS browser profile.")

            result = page.evaluate(
                """async ({partySize, start, end, facilityId, token}) => {
                  try {
                    const resp = await fetch(
                      `/dine-res/api/availability/${partySize}/${start},${end}?facilityId=${facilityId}&entityType=restaurant`,
                      { headers: {
                        'Authorization': token,
                        'x-function-name': 'getAvailability',
                        'x-disney-internal-dine-vas-365': 'true',
                        'x-disney-internal-dine-vas-eks': 'true',
                        'accept': 'application/json, text/plain, */*',
                      }}
                    );
                    return { status: resp.status, data: resp.status === 200 ? await resp.json() : null };
                  } catch (e) {
                    return { status: 0, error: String(e) };
                  }
                }""",
                {
                    "partySize": party_size,
                    "start": start,
                    "end": end,
                    "facilityId": facility_id,
                    "token": token,
                },
            )
        finally:
            context.close()

    if result.get("status") != 200:
        raise RuntimeError(f"[monitor] {name}: HTTP {result.get('status')} from availability API {result.get('error', '')}")
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
            if not token:
                raise RuntimeError("No Disney auth token found in Playwright profile. Log in on the VPS browser profile.")
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


def check_slots_for_restaurant(restaurant: dict) -> List[Slot]:
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
