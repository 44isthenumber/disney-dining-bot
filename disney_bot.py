"""
Disney dining reservation monitor — main entry point.

Usage:
    python disney_bot.py           # start polling loop
    python disney_bot.py --once    # single poll then exit (good for testing)
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set

import schedule
import yaml
from dotenv import load_dotenv

import storage
from auth import get_valid_token
from monitor import Slot, check_restaurant, check_slots_via_chrome
from notify import send_sms

load_dotenv()


def load_config() -> dict:
    text = storage.read_text("config.yaml", "")
    if not text:
        return {"restaurants": []}
    return yaml.safe_load(text) or {"restaurants": []}


# ── dedup / cooldown ───────────────────────────────────────────────────────
# Track (facility_id, date, time, party_size) → last-alerted timestamp.
# Re-alert after alert_cooldown_minutes so you don't miss a slot that keeps
# opening and closing.

_seen: Dict[tuple, datetime] = {}


def filter_new(slots: List[Slot], cooldown_minutes: int) -> List[Slot]:
    now = datetime.now()
    new = []
    for s in slots:
        key = (s.facility_id, s.date, s.time, s.party_size)
        last = _seen.get(key)
        if last is None or (now - last) > timedelta(minutes=cooldown_minutes):
            new.append(s)
            _seen[key] = now
    return new


# ── poll ───────────────────────────────────────────────────────────────────

def poll(config: dict) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] Polling {len(config['restaurants'])} restaurant(s) …")

    all_slots: List[Slot] = []
    for restaurant in config["restaurants"]:
        name = restaurant.get("name", "?")
        try:
            slots = check_slots_via_chrome(restaurant)
            all_slots.extend(slots)
            if slots:
                print(f"[bot] {name}: {len(slots)} slot(s) found.")
            else:
                print(f"[bot] {name}: no availability.")
        except Exception as e:
            print(f"[bot] Chrome check failed for {name}: {e}")

    cooldown = config.get("alert_cooldown_minutes", 60)
    new_slots = filter_new(all_slots, cooldown)
    if new_slots:
        print(f"[bot] Sending alert for {len(new_slots)} new slot(s).")
        send_sms(new_slots)
    else:
        print("[bot] No new slots to alert on.")

    storage.write_json("bot_state.json", {
        "last_poll_at": datetime.utcnow().isoformat() + "Z",
        "slots_found_last_poll": len(new_slots),
    })


# ── entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Disney dining availability monitor")
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single poll and exit (useful for testing)"
    )
    args = parser.parse_args()

    config = load_config()
    interval = config.get("polling_interval_minutes", 10)

    if args.once:
        poll(config)
        return

    print(f"[bot] Starting — polling every {interval} minute(s).  Ctrl-C to stop.")
    poll(config)  # immediate first check

    schedule.every(interval).minutes.do(poll, config=config)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n[bot] Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
