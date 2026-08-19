#!/usr/bin/env python3
"""Safe production smoke test for Magic Table Finder.

This verifies the website API without sending SMS:
- signup/login is session-cookie based (no public /profiles directory)
- status is readable for the signed-in owner
- a fake future watch can be created for the selected owner
- the watch is owner-scoped
- cleanup deletes the generated watch IDs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://magictablefinder.com/_api"
FAKE_DATE = "2099-01-01"
FAKE_RESTAURANT = {
    "facility_id": "90002686",
    "name": "Smoke Test Restaurant",
    "slug": "smoke-test-restaurant",
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value.strip().strip("'\""))


def password_for(user_id: str) -> str:
    raw = os.environ.get("WATCH_USERS") or os.environ.get("DISNEY_USERS") or ""
    if raw.strip():
        try:
            parsed = json.loads(raw)
            password = str((parsed.get(user_id) or {}).get("password") or "").strip()
            if password:
                return password
        except json.JSONDecodeError:
            pass
    return os.environ.get("API_SECRET", "")


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def login(self, identifier: str, password: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/login",
            json={"identifier": identifier, "password": password},
            timeout=20,
        )
        try:
            data = response.json()
        except ValueError:
            data = {"detail": response.text}
        if response.status_code >= 400:
            detail = data.get("detail") or data.get("error") or response.reason
            raise RuntimeError(f"POST /login failed for {identifier}: {response.status_code} {detail}")
        return data

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(method, f"{self.base_url}{path}", timeout=20, **kwargs)
        if response.status_code == 204:
            return None
        try:
            data = response.json()
        except ValueError:
            data = {"detail": response.text}
        if response.status_code >= 400:
            detail = data.get("detail") or data.get("error") or response.reason
            raise RuntimeError(f"{method} {path} failed: {response.status_code} {detail}")
        return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a safe live API smoke test.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--user-id", default=os.environ.get("DEFAULT_OWNER_ID", "craig"))
    parser.add_argument("--date", default=FAKE_DATE)
    args = parser.parse_args()

    load_dotenv(Path(".env"))
    secret = password_for(args.user_id)
    if not secret:
        print("A per-user WATCH_USERS password (or API_SECRET fallback) is required", file=sys.stderr)
        return 2

    profiles_probe = requests.get(f"{args.base_url.rstrip('/')}/profiles", timeout=20)
    if profiles_probe.status_code != 404:
        print(f"/profiles must not be a public directory (got {profiles_probe.status_code})", file=sys.stderr)
        return 1
    print("profiles: hidden (404)")

    other_ids = ["craig", "Jessica"]
    clients: dict[str, ApiClient] = {}
    for profile_id in other_ids:
        password = password_for(profile_id)
        if not password:
            continue
        client = ApiClient(args.base_url)
        client.login(profile_id, password)
        clients[profile_id] = client

    if args.user_id not in clients:
        print(f"could not sign in as {args.user_id!r}", file=sys.stderr)
        return 1

    client = clients[args.user_id]
    created_ids: list[str] = []
    try:
        for profile_id, profile_client in clients.items():
            status = profile_client.request("GET", "/status")
            profile = (status.get("profile") or {}).get("id")
            print(f"status[{profile_id}]: {status.get('session_status')} watches={status.get('watches_count')} owner={profile}")

        payload = {
            **FAKE_RESTAURANT,
            "party_size": 2,
            "dates": [args.date],
            "meal_periods": ["DINNER"],
            "time_from": "17:00",
            "time_to": "19:00",
        }
        created = client.request("POST", "/watches", data=json.dumps(payload))
        created_ids = created.get("added", [])
        if not created_ids:
            raise RuntimeError("POST /watches returned no created IDs")
        print(f"created: {', '.join(created_ids)}")

        watches = client.request("GET", "/watches").get("watches", [])
        found = [watch for watch in watches if watch.get("watch_id") in created_ids]
        if len(found) != len(created_ids):
            raise RuntimeError("created smoke watch was not visible to its owner")
        if any(watch.get("owner_id") != args.user_id for watch in found):
            raise RuntimeError("created smoke watch has the wrong owner")
        print(f"verified owner scope: {args.user_id}")

        for profile_id, profile_client in clients.items():
            if profile_id == args.user_id:
                continue
            other_watches = profile_client.request("GET", "/watches").get("watches", [])
            leaks = [watch.get("watch_id") for watch in other_watches if watch.get("watch_id") in created_ids]
            if leaks:
                raise RuntimeError(f"smoke watch leaked into {profile_id}: {', '.join(leaks)}")
        print("verified cross-profile isolation")

    finally:
        for watch_id in created_ids:
            try:
                client.request("DELETE", f"/watches/{watch_id}")
                print(f"deleted: {watch_id}")
            except Exception as exc:  # noqa: BLE001 - cleanup must report every failure
                print(f"cleanup failed for {watch_id}: {exc}", file=sys.stderr)

    remaining = client.request("GET", "/watches").get("watches", [])
    leftovers = [watch.get("watch_id") for watch in remaining if watch.get("watch_id") in created_ids]
    if leftovers:
        print(f"leftover smoke watches: {', '.join(leftovers)}", file=sys.stderr)
        return 1

    print(f"smoke test passed for {args.user_id} on {date.today().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
