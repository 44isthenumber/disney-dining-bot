"""
One-off script: fetch all WDW dining facilities and write restaurants.json.

Run:
    cd ~/Documents/disney-dining-bot
    python3 index_restaurants.py

Re-run whenever the restaurant list changes (monthly is fine).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests as cffi_requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from auth import get_valid_token  # noqa: E402 — needs dotenv loaded first

FACILITIES_URL = "https://disneyworld.disney.go.com/dine-res/api/dine/facilities"
OUT_FILE = Path(__file__).parent / "restaurants.json"


def _slug_from_url(url_friendly_id: str) -> str:
    """Extract last path segment: 'http://.../jaleo/' → 'jaleo'"""
    parts = url_friendly_id.rstrip("/").split("/")
    return parts[-1] if parts else ""


def _media_url(item: dict) -> str:
    media = item.get("media", {})
    for key in ("finderListMobileSquare", "finderStandardThumb", "finderDetailNarrowHero"):
        entry = media.get(key)
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    return ""


def _extract(item: dict, dining_type: str) -> dict:
    raw_id = str(item.get("id", ""))
    facility_id = raw_id.split(";")[0]
    url_friendly = item.get("urlFriendlyId", "")
    slug = _slug_from_url(url_friendly)
    park = item.get("ancestorLocationParkResort", "")
    cuisine = item.get("primaryCuisineType", "")
    experience = item.get("experienceType", "")
    return {
        "facility_id": facility_id,
        "name": item.get("name", ""),
        "slug": slug,
        "park": park,
        "cuisine": cuisine,
        "experience_type": experience,
        "dining_type": dining_type,
        "meal_period": item.get("mealPeriodType", ""),
        "thumbnail_url": _media_url(item),
        "booking_url": (
            f"https://disneyworld.disney.go.com/dine-res/restaurant/{slug}"
            if slug else ""
        ),
        "price_range": item.get("priceRange", ""),
        "description": item.get("description", "").strip(),
    }


def main() -> None:
    token = get_valid_token()
    cookies = {
        "SWID": os.environ.get("DISNEY_SWID", ""),
        "akacd_dineplan": os.environ.get("DISNEY_AKACD", ""),
        "_abck": os.environ.get("DISNEY_ABCK", ""),
        "bm_sz": os.environ.get("DISNEY_BM_SZ", ""),
    }
    headers = {
        "Authorization": f"BEARER {token}",
        "accept": "application/json, text/plain, */*",
        "x-function-name": "getAllFacilities",
        "x-disney-internal-dine-vas-365": "true",
        "x-disney-internal-dine-vas-eks": "true",
        "x-conversation-id": str(uuid.uuid4()),
        "x-correlation-id": str(uuid.uuid4()),
        "referer": "https://disneyworld.disney.go.com/dine-res",
    }

    print("[indexer] Fetching facilities …")
    resp = cffi_requests.get(
        FACILITIES_URL, headers=headers, cookies=cookies,
        impersonate="chrome120", timeout=30,
    )
    print(f"[indexer] Status: {resp.status_code}  |  Body: {len(resp.content)} bytes")
    resp.raise_for_status()
    data = resp.json()

    restaurants: list = []
    for dining_type, key in [
        ("restaurant", "restaurant"),
        ("dinnerShow", "dinnerShow"),
        ("diningEvent", "diningEvent"),
    ]:
        items = data.get(key, {})
        if isinstance(items, list):
            items = {str(i): v for i, v in enumerate(items)}
        for item in items.values():
            if not item:
                continue
            restaurants.append(_extract(item, dining_type))

    restaurants.sort(key=lambda r: r["name"])

    out = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "count": len(restaurants),
        "restaurants": restaurants,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[indexer] Wrote {len(restaurants)} restaurants → {OUT_FILE}")

    # Spot-check
    jaleo = next((r for r in restaurants if "jaleo" in r["name"].lower()), None)
    if jaleo:
        print(f"[indexer] Spot-check Jaleo: facility_id={jaleo['facility_id']} slug={jaleo['slug']}")


if __name__ == "__main__":
    main()
