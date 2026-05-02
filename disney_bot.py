"""Self-hosted Disney dining monitor worker.

Usage:
    python disney_bot.py           # start polling loop
    python disney_bot.py --once    # single poll then exit
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from dataclasses import replace
from typing import Dict, List, Optional

import schedule
import yaml
from dotenv import load_dotenv

import storage
import watch_store
from monitor import Slot, check_slots_for_restaurant
from notify import send_sms

load_dotenv()


def load_config() -> dict:
    text = storage.read_text("config.yaml", "")
    if not text:
        return {"restaurants": []}
    return yaml.safe_load(text) or {"restaurants": []}


# ── dedup / cooldown ───────────────────────────────────────────────────────

def _slot_key(slot: Slot) -> str:
    return "__".join([
        slot.watch_id or slot.owner_id or "unknown",
        slot.facility_id,
        slot.date,
        slot.time,
        str(slot.party_size),
    ])


def _load_seen() -> Dict[str, str]:
    data = storage.read_json("seen_slots.json") or {}
    if isinstance(data, dict) and isinstance(data.get("slots"), dict):
        return data["slots"]
    if isinstance(data, dict):
        return data
    return {}


def _save_seen(seen: Dict[str, str]) -> None:
    storage.write_json("seen_slots.json", {
        "schema_version": 1,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "slots": seen,
    })


def filter_new(slots: List[Slot], cooldown_minutes: int) -> List[Slot]:
    now = datetime.now()
    seen = _load_seen()
    new = []
    for s in slots:
        key = _slot_key(s)
        last_raw = seen.get(key)
        last = None
        if last_raw:
            try:
                last = datetime.fromisoformat(last_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                last = None
        if last is None or (now - last) > timedelta(minutes=cooldown_minutes):
            new.append(s)
            seen[key] = now.isoformat() + "Z"
    _save_seen(seen)
    return new


# ── poll ───────────────────────────────────────────────────────────────────

def _matching_owner_slots(slots: List[Slot], watches: List[dict]) -> List[Slot]:
    matched: List[Slot] = []
    for slot in slots:
        for watch in watches:
            if slot.facility_id != watch["facility_id"]:
                continue
            if slot.date != watch["date"]:
                continue
            if slot.party_size != int(watch.get("party_size", 2)):
                continue
            matched.append(replace(
                slot,
                owner_id=watch["owner_id"],
                watch_id=watch["watch_id"],
                recipient_phone=watch.get("recipient_phone", ""),
                slug=watch.get("slug") or slot.slug,
            ))
    return matched


def poll(config: Optional[dict] = None) -> None:
    config = config or load_config()
    watches = watch_store.load_watches()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    grouped = watch_store.grouped_restaurant_requests(watches)
    print(f"\n[{ts}] Polling {len(watches)} watch(es) across {len(grouped)} restaurant request(s) …")

    all_slots: List[Slot] = []
    errors = []
    for restaurant in grouped:
        name = restaurant.get("name", "?")
        try:
            slots = check_slots_for_restaurant(restaurant)
            owner_slots = _matching_owner_slots(slots, restaurant.get("watches", []))
            all_slots.extend(owner_slots)
            if owner_slots:
                print(f"[bot] {name}: {len(owner_slots)} owner-matched slot alert candidate(s).")
            else:
                print(f"[bot] {name}: no availability.")
        except Exception as e:
            errors.append({"restaurant": name, "error": str(e)})
            print(f"[bot] Check failed for {name}: {e}")

    cooldown = config.get("alert_cooldown_minutes", 60)
    new_slots = filter_new(all_slots, cooldown)
    if new_slots:
        print(f"[bot] Sending alert for {len(new_slots)} new slot(s).")
        send_sms(new_slots)
    else:
        print("[bot] No new slots to alert on.")

    now_utc = datetime.utcnow().isoformat() + "Z"
    previous_state = storage.read_json("bot_state.json") or {}
    storage.write_json("bot_state.json", {
        "last_poll_at": now_utc,
        "last_successful_poll_at": now_utc if not errors else previous_state.get("last_successful_poll_at"),
        "slots_found_last_poll": len(new_slots),
        "watch_count": len(watches),
        "restaurant_request_count": len(grouped),
        "last_errors": errors,
        "session_status": "needs_attention" if errors else "ok",
        "last_sms_sent_at": now_utc if new_slots else previous_state.get("last_sms_sent_at"),
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
    interval = int(config.get("polling_interval_minutes", 10))

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
