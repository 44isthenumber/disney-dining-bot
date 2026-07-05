#!/usr/bin/env python3
"""Read-only smoke test for the scheduled-activity (Enchanting Extras) path.

Runs the live sa-api checker for Harmony Barber Shop using the persistent
Playwright profile. No Gist writes, no SMS, no watch mutations.

Run on the VPS:
    cd /opt/disney-dining-bot && . .venv/bin/activate
    xvfb-run -a python3 scripts/smoke_test_sa_api.py [--days 9] [--calendar]
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import monitor  # noqa: E402

HARMONY = {
    "facility_id": "15437454",
    "slug": "booking-harmony-barber-shop",
    "name": "Harmony Barber Shop",
    "party_size": 2,
    "meal_periods": ["ALL"],
    "booking_type": "scheduled_activity",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=9, help="How many days ahead to check (default 9)")
    parser.add_argument("--calendar", action="store_true", help="Also sweep the full calendar (slow, ~7 requests)")
    args = parser.parse_args()

    start = date.today() + timedelta(days=1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(args.days)]
    request = dict(HARMONY, dates=dates)

    print(f"[sa-smoke] Checking {HARMONY['name']} for {dates[0]}..{dates[-1]} party of {HARMONY['party_size']}")
    print(f"[sa-smoke] Window chunks: {monitor._sa_date_windows(dates)}")
    slots = monitor.check_scheduled_activity_slots_via_playwright(request)
    for slot in slots:
        print(f"[sa-smoke]   OPEN {slot.date} {slot.label} ({slot.meal_period}) key-safe={bool(slot.meal_period)}")
    if not slots:
        print("[sa-smoke] No open slots in range (expected — Harmony is usually sold out).")

    if args.calendar:
        print("[sa-smoke] Sweeping full calendar…")
        days = monitor.get_scheduled_activity_calendar_days_via_playwright(
            HARMONY["facility_id"], HARMONY["slug"], HARMONY["party_size"]
        )
        print(f"[sa-smoke] {len(days)} date(s) with availability: {days}")

    print("[sa-smoke] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
