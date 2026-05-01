#!/usr/bin/env python3
"""Cache Disney calendar availability for watched restaurants into the gist."""
from datetime import datetime
import yaml
import storage
from auth import get_valid_token
from monitor import get_available_calendar_days


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
    token = get_valid_token()
    for r in restaurants:
        fid = r["facility_id"]
        slug = r.get("slug", fid)
        name = r.get("name", fid)
        try:
            available = sorted(get_available_calendar_days(fid, token, slug))
            storage.write_json(f"calendar_{fid}.json", {
                "facility_id": fid,
                "available_dates": available,
                "cached_at": datetime.utcnow().isoformat() + "Z",
            })
            print(f"[cache] {name}: {len(available)} available dates")
        except Exception as e:
            print(f"[cache] Error for {name}: {e}")


if __name__ == "__main__":
    update_cache()
