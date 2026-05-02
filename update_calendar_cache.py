#!/usr/bin/env python3
"""Cache Disney calendar availability for watched restaurants into the gist.

Strategy: navigate Chrome to each restaurant's own page before fetching.
Akamai allows one API call per fresh page load — navigating first guarantees
a 200. All fetches run inside the real Chrome tab via AppleScript so cookies
are always valid.

Requires:
- Chrome open with a disneyworld.disney.go.com tab
- View → Developer → Allow JavaScript from Apple Events (one-time setup)
"""
import base64
import json
import re
import subprocess
import time
from datetime import datetime

import yaml
import storage


# ── Chrome helpers ─────────────────────────────────────────────────────────

def _get_token_from_chrome() -> str:
    """Extract the Disney access token from Chrome's cookie store."""
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
                        remaining = payload.get("exp", 0) - time.time()
                        if 0 < remaining < 86400:
                            return f"BEARER {jwt}"
                    except Exception:
                        pass
    except Exception as e:
        print(f"[cache] Warning: could not read token from Chrome: {e}")
    import os
    return f"BEARER {os.environ.get('DISNEY_ACCESS_TOKEN', '')}"


def _run_js(js: str, timeout: int = 12) -> str:
    """Run JS in the Disney Chrome tab via AppleScript. Returns string result."""
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
    result = subprocess.check_output(
        ["osascript", "-e", script],
        stderr=subprocess.PIPE,
        timeout=timeout,
    ).decode().strip()
    return result


def _navigate_disney_tab(url: str, timeout: int = 8) -> None:
    """Navigate the Disney Chrome tab to url, then wait for it to load."""
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
        return "ERROR: no Disney tab open"
    end if
    set URL of disneyTab to {json.dumps(url)}
    return "ok"
end tell
"""
    subprocess.check_output(["osascript", "-e", script], stderr=subprocess.PIPE, timeout=timeout)


# ── Calendar fetch ─────────────────────────────────────────────────────────

def _fetch_calendar_for_restaurant(fid: str, slug: str, token: str) -> list:
    """
    Navigate to the restaurant page, then fetch calendar-days.
    Returns sorted list of available date strings.
    """
    url = f"https://disneyworld.disney.go.com/dine-res/restaurant/{slug}"
    _navigate_disney_tab(url)
    time.sleep(8)  # wait for page load + Akamai warm-up

    fire_js = f"""
window._calResult = null;
(async function() {{
  const tok = {json.dumps(token)};
  try {{
    const resp = await fetch('/dine-res/api/calendar-days?facilityId={fid}&entityType=restaurant', {{
      headers: {{
        'Authorization': tok,
        'x-function-name': 'getCalendarDays',
        'x-disney-internal-dine-vas-365': 'true',
        'x-disney-internal-dine-vas-eks': 'true',
        'accept': 'application/json, text/plain, */*',
      }}
    }});
    const data = await resp.json();
    if (resp.status !== 200) {{
      window._calResult = JSON.stringify({{status: resp.status, dates: []}});
      return;
    }}
    const r = data.bookingDateRanges;
    let dates = [];
    if (r) {{
      const ranges = Array.isArray(r) ? r : [r];
      for (const rng of ranges) {{
        let cur = new Date(rng.startDate + 'T00:00:00Z');
        const last = new Date(rng.endDate + 'T00:00:00Z');
        while (cur <= last) {{
          dates.push(cur.toISOString().slice(0, 10));
          cur.setUTCDate(cur.getUTCDate() + 1);
        }}
      }}
    }}
    window._calResult = JSON.stringify({{status: 200, dates: [...new Set(dates)].sort()}});
  }} catch(e) {{
    window._calResult = JSON.stringify({{status: 0, dates: [], error: String(e)}});
  }}
}})();
'fired'
"""
    out = _run_js(fire_js, timeout=12)
    if out.startswith("ERROR"):
        raise RuntimeError(out)

    # Poll for result (max 25s)
    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(3)
        raw = _run_js("String(window._calResult)", timeout=8)
        if raw and raw not in ("null", "undefined"):
            result = json.loads(raw)
            if result["status"] != 200:
                raise RuntimeError(f"HTTP {result['status']} {result.get('error', '')}")
            return result["dates"]

    raise RuntimeError("Timed out waiting for calendar fetch result")


# ── Main ───────────────────────────────────────────────────────────────────

def update_cache():
    text = storage.read_text("config.yaml", "")
    if not text:
        print("[cache] No config.yaml — nothing to cache.")
        return
    config = yaml.safe_load(text) or {}
    restaurants = config.get("restaurants", [])
    if not restaurants:
        print("[cache] Watch list empty.")
        return

    token = _get_token_from_chrome()
    now = datetime.utcnow().isoformat() + "Z"

    for r in restaurants:
        fid = r["facility_id"]
        slug = r.get("slug", fid)
        name = r.get("name", fid)
        try:
            dates = _fetch_calendar_for_restaurant(fid, slug, token)
            storage.write_json(f"calendar_{fid}.json", {
                "facility_id": fid,
                "available_dates": dates,
                "cached_at": now,
            })
            print(f"[cache] {name}: {len(dates)} available dates")
        except Exception as e:
            print(f"[cache] Error for {name}: {e}")


if __name__ == "__main__":
    update_cache()
