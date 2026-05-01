"""Twilio SMS notifications for Disney dining availability alerts."""

import os
from typing import List

from dotenv import load_dotenv
from twilio.rest import Client

from monitor import Slot

load_dotenv()

BOOK_BASE = "https://disneyworld.disney.go.com/dine-res/restaurant"


def _format_message(slots: List[Slot]) -> str:
    lines = ["Disney Dining Alert!"]
    # Group by restaurant + date for readability
    by_restaurant: dict = {}
    for s in slots:
        key = (s.restaurant_name, s.date)
        by_restaurant.setdefault(key, []).append(s)

    for (name, date), group in sorted(by_restaurant.items()):
        times = ", ".join(sorted(set(s.time for s in group)))
        party = group[0].party_size
        meal = group[0].meal_period
        slug = name.lower().replace(" ", "-").replace("'", "").replace(",", "")
        url = f"{BOOK_BASE}/{group[0].facility_id}"
        lines.append(f"\n{name}")
        lines.append(f"Date: {date} | Party of {party} | {meal}")
        lines.append(f"Times: {times}")
        lines.append(f"Book: {url}")

    return "\n".join(lines)


def send_sms(slots: List[Slot]) -> None:
    if not slots:
        return

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM", "")
    to_number = os.environ.get("TWILIO_TO", "")

    if not all([account_sid, auth_token, from_number, to_number]):
        print("[notify] Twilio credentials not set — printing alert instead:")
        print(_format_message(slots))
        return

    client = Client(account_sid, auth_token)
    body = _format_message(slots)
    message = client.messages.create(body=body, from_=from_number, to=to_number)
    print(f"[notify] SMS sent ({len(slots)} slot(s)). SID: {message.sid}")
