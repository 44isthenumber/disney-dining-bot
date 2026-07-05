#!/usr/bin/env python3
"""Cache Disney calendar availability for watched restaurants.

Production uses the same persistent Playwright browser profile as the polling
worker, so the cache updater can run on a VPS without a desktop Chrome tab.
"""
from datetime import datetime, timezone

from dotenv import load_dotenv

import storage
import watch_store
from monitor import (
    get_calendar_days_via_playwright,
    get_scheduled_activity_calendar_days_via_playwright,
)

load_dotenv()


# ── Main ───────────────────────────────────────────────────────────────────

def update_cache():
    watches = watch_store.load_watches()
    restaurants = watch_store.grouped_restaurant_requests(watches)
    if not restaurants:
        print("[cache] Watch list empty.")
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    for r in restaurants:
        fid = r["facility_id"]
        slug = r.get("slug", fid)
        name = r.get("name", fid)
        try:
            if (r.get("booking_type") or "dining") == "scheduled_activity":
                dates = get_scheduled_activity_calendar_days_via_playwright(
                    fid, slug, r.get("party_size", 2)
                )
            else:
                dates = get_calendar_days_via_playwright(fid, slug)
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
