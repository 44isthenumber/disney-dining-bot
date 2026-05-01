"""
FastAPI backend for the Disney dining bot frontend.

Run:
    uvicorn api:app --port 8080 --reload

Endpoints:
    GET  /status
    GET  /restaurants?q=&park=&cuisine=
    GET  /calendar/{facility_id}?party_size=2
    GET  /watches
    POST /watches
    DELETE /watches/{watch_id}
"""

import json
import os
import time
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from auth import _jwt_exp, get_valid_token, load_tokens  # noqa: E402
from monitor import get_available_calendar_days  # noqa: E402

CONFIG_FILE = Path(__file__).parent / "config.yaml"
RESTAURANTS_FILE = Path(__file__).parent / "restaurants.json"
BOT_STATE_FILE = Path(__file__).parent / "bot_state.json"

app = FastAPI(title="Disney Dining Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://(.*\.carrd\.co|.*\.ngrok-free\.app|localhost(:\d+)?)",
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── auth middleware ────────────────────────────────────────────────────────────

def _check_secret(request: Request, x_api_secret: Optional[str] = Header(default=None)):
    secret = os.environ.get("API_SECRET", "").strip()
    if not secret:
        return  # no secret configured → open access (dev mode)
    if request.method == "OPTIONS":
        return  # CORS preflight
    if x_api_secret != secret:
        raise HTTPException(status_code=401, detail="Invalid API secret")


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {"restaurants": []}
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {"restaurants": []}


def _save_config(cfg: dict) -> None:
    tmp = CONFIG_FILE.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    os.replace(tmp, CONFIG_FILE)


def _watch_id(facility_id: str, party_size: int, date: str) -> str:
    return f"{facility_id}__{party_size}__{date}"


def _parse_watch_id(watch_id: str):
    parts = watch_id.split("__")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Invalid watch_id format")
    facility_id, party_size_str, date = parts
    return facility_id, int(party_size_str), date


# ── models ────────────────────────────────────────────────────────────────────

class WatchRequest(BaseModel):
    facility_id: str
    name: str
    slug: str
    party_size: int = 2
    meal_periods: List[str] = ["ALL"]
    dates: List[str]


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/status", dependencies=[Depends(_check_secret)])
def get_status():
    token_status = "ok"
    token_expires_in_minutes = None
    try:
        tokens = load_tokens()
        exp = _jwt_exp(tokens["access_token"])
        token_expires_in_minutes = int((exp - time.time()) / 60)
        if token_expires_in_minutes < 0:
            token_status = "expired"
    except Exception as e:
        token_status = f"error: {e}"

    last_poll_at = None
    slots_found_last_poll = None
    if BOT_STATE_FILE.exists():
        try:
            state = json.loads(BOT_STATE_FILE.read_text())
            last_poll_at = state.get("last_poll_at")
            slots_found_last_poll = state.get("slots_found_last_poll")
        except Exception:
            pass

    restaurants_indexed = 0
    if RESTAURANTS_FILE.exists():
        try:
            restaurants_indexed = json.loads(RESTAURANTS_FILE.read_text()).get("count", 0)
        except Exception:
            pass

    cfg = _load_config()
    watches_count = sum(len(r.get("dates", [])) for r in cfg.get("restaurants", []))

    return {
        "token_status": token_status,
        "token_expires_in_minutes": token_expires_in_minutes,
        "last_poll_at": last_poll_at,
        "slots_found_last_poll": slots_found_last_poll,
        "watches_count": watches_count,
        "restaurants_indexed": restaurants_indexed,
    }


@app.get("/restaurants", dependencies=[Depends(_check_secret)])
def list_restaurants(q: str = "", park: str = "", cuisine: str = ""):
    if not RESTAURANTS_FILE.exists():
        raise HTTPException(status_code=503, detail="restaurants.json not found — run index_restaurants.py first")
    data = json.loads(RESTAURANTS_FILE.read_text())
    results = data.get("restaurants", [])

    if q:
        q_lower = q.lower()
        results = [r for r in results if q_lower in r["name"].lower()]
    if park:
        park_lower = park.lower()
        results = [r for r in results if park_lower in r["park"].lower()]
    if cuisine:
        cuisine_lower = cuisine.lower()
        results = [r for r in results if cuisine_lower in r["cuisine"].lower()]

    # Include which dates are currently being watched per restaurant
    cfg = _load_config()
    watched: dict = {}
    for entry in cfg.get("restaurants", []):
        watched[entry["facility_id"]] = {
            "party_size": entry.get("party_size", 2),
            "dates": entry.get("dates", []),
        }

    for r in results:
        w = watched.get(r["facility_id"])
        r["watched_dates"] = w["dates"] if w else []
        r["watched_party_size"] = w["party_size"] if w else None

    return {"restaurants": results, "total": len(results)}


@app.get("/calendar/{facility_id}", dependencies=[Depends(_check_secret)])
def get_calendar(facility_id: str, party_size: int = 2):
    # Fetch slug from restaurants.json
    slug = facility_id
    if RESTAURANTS_FILE.exists():
        data = json.loads(RESTAURANTS_FILE.read_text())
        match = next((r for r in data["restaurants"] if r["facility_id"] == facility_id), None)
        if match:
            slug = match.get("slug", facility_id)

    try:
        token = get_valid_token()
        available_dates = sorted(get_available_calendar_days(facility_id, token, slug))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"facility_id": facility_id, "available_dates": available_dates}


@app.get("/watches", dependencies=[Depends(_check_secret)])
def get_watches():
    cfg = _load_config()
    watches = []
    for entry in cfg.get("restaurants", []):
        fid = entry["facility_id"]
        ps = int(entry.get("party_size", 2))
        for d in entry.get("dates", []):
            watches.append({
                "watch_id": _watch_id(fid, ps, d),
                "facility_id": fid,
                "name": entry.get("name", fid),
                "slug": entry.get("slug", fid),
                "party_size": ps,
                "meal_periods": entry.get("meal_periods", ["ALL"]),
                "date": d,
            })
    return {"watches": watches}


@app.post("/watches", dependencies=[Depends(_check_secret)], status_code=201)
def add_watch(body: WatchRequest):
    cfg = _load_config()
    restaurants = cfg.setdefault("restaurants", [])

    # Find existing entry for same facility + party_size
    existing = next(
        (r for r in restaurants
         if r["facility_id"] == body.facility_id and int(r.get("party_size", 2)) == body.party_size),
        None,
    )
    if existing:
        current_dates = set(existing.get("dates", []))
        new_dates = current_dates | set(body.dates)
        existing["dates"] = sorted(new_dates)
        existing["meal_periods"] = body.meal_periods
        existing["name"] = body.name
        existing["slug"] = body.slug
    else:
        restaurants.append({
            "facility_id": body.facility_id,
            "name": body.name,
            "slug": body.slug,
            "party_size": body.party_size,
            "meal_periods": body.meal_periods,
            "dates": sorted(set(body.dates)),
        })

    _save_config(cfg)
    added = [_watch_id(body.facility_id, body.party_size, d) for d in body.dates]
    return {"added": added}


@app.delete("/watches/{watch_id}", dependencies=[Depends(_check_secret)], status_code=204)
def remove_watch(watch_id: str):
    facility_id, party_size, date = _parse_watch_id(watch_id)
    cfg = _load_config()
    restaurants = cfg.get("restaurants", [])

    for entry in restaurants:
        if entry["facility_id"] == facility_id and int(entry.get("party_size", 2)) == party_size:
            dates = entry.get("dates", [])
            if date in dates:
                dates.remove(date)
                entry["dates"] = dates
            break

    # Remove entries with no dates remaining
    cfg["restaurants"] = [r for r in restaurants if r.get("dates")]
    _save_config(cfg)
