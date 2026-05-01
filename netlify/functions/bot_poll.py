"""
Netlify Scheduled Function: poll Disney dining availability every 10 minutes.
Schedule is defined in netlify.toml under [functions."bot_poll"].
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
import storage
from auth import get_valid_token
from monitor import Slot, check_restaurant
from notify import send_sms


def _filter_new(slots, cooldown_minutes, seen):
    from datetime import timedelta
    now = datetime.now()
    new = []
    for s in slots:
        key = f"{s.facility_id}|{s.date}|{s.time}|{s.party_size}"
        last_str = seen.get(key)
        if last_str is None:
            new.append(s)
            seen[key] = now.isoformat()
        else:
            last = datetime.fromisoformat(last_str)
            if (now - last).total_seconds() > cooldown_minutes * 60:
                new.append(s)
                seen[key] = now.isoformat()
    return new


def handler(event, context):
    print(f"[bot_poll] Starting poll at {datetime.utcnow().isoformat()}Z")

    config_text = storage.read_text("config.yaml", "")
    if not config_text:
        print("[bot_poll] No config.yaml found — nothing to watch.")
        return {"statusCode": 200, "body": "no config"}

    config = yaml.safe_load(config_text) or {}
    restaurants = config.get("restaurants", [])
    if not restaurants:
        print("[bot_poll] Watch list is empty.")
        return {"statusCode": 200, "body": "empty watch list"}

    cooldown = config.get("alert_cooldown_minutes", 60)

    # Load persistent seen-slots state
    seen = storage.read_json("seen_slots.json") or {}

    try:
        token = get_valid_token()
    except Exception as e:
        print(f"[bot_poll] Token error: {e}")
        return {"statusCode": 500, "body": str(e)}

    all_slots = []
    for restaurant in restaurants:
        try:
            slots = check_restaurant(restaurant, token)
            all_slots.extend(slots)
            print(f"[bot_poll] {restaurant.get('name', '?')}: {len(slots)} slot(s)")
        except Exception as e:
            print(f"[bot_poll] Error checking {restaurant.get('name', '?')}: {e}")

    new_slots = _filter_new(all_slots, cooldown, seen)
    storage.write_json("seen_slots.json", seen)

    if new_slots:
        print(f"[bot_poll] Alerting on {len(new_slots)} new slot(s).")
        send_sms(new_slots)
    else:
        print("[bot_poll] No new slots.")

    storage.write_json("bot_state.json", {
        "last_poll_at": datetime.utcnow().isoformat() + "Z",
        "slots_found_last_poll": len(new_slots),
    })

    return {"statusCode": 200, "body": f"polled {len(restaurants)} restaurants, {len(new_slots)} new slots"}
