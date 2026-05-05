"""Twilio SMS notifications for Disney dining availability alerts."""

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List
from urllib.parse import urlencode

from dotenv import load_dotenv
from twilio.rest import Client

from monitor import Slot

load_dotenv()

BOOK_BASE = "https://disneyworld.disney.go.com/dine-res/book/table-service/details"
MAX_MESSAGE_LENGTH = 1500


@dataclass
class SendResult:
    sent_slots: List[Slot]
    errors: List[str]


def booking_url(slot: Slot) -> str:
    params = {
        "date": slot.date,
        "partySize": str(slot.party_size),
    }
    if slot.time:
        params["time"] = slot.time
    if slot.offer_id:
        params["offerId"] = slot.offer_id
    return f"{BOOK_BASE}/{slot.facility_id}/?{urlencode(params)}"


def _format_message(slots: List[Slot]) -> str:
    title = "Disney Dining Alert!" if len(slots) == 1 else f"Disney Dining Alert! {len(slots)} new openings"
    lines = [title]

    for slot in sorted(slots, key=lambda s: (s.date, s.restaurant_name, s.time, s.party_size)):
        time_label = slot.label or slot.time
        lines.append(f"\nNew opening: {slot.restaurant_name}")
        lines.append(f"{slot.date} at {time_label} | Party of {slot.party_size} | {slot.meal_period}")
        lines.append(f"Book exact slot: {booking_url(slot)}")

    lines.append("\nReply STOP to opt out. Reply HELP for help.")
    return "\n".join(lines)


A2P_FOOTER = "\n\nReply STOP to opt out. Reply HELP for help."


def send_operational_sms(to_numbers: List[str], body: str) -> List[str]:
    """Send a one-off operational message to explicit numbers (session alerts, etc.).

    Appends the A2P compliance footer when the body does not already include STOP/HELP.
    Returns a list of human-readable errors for sends that failed.
    """
    deduped = list(dict.fromkeys(p.strip() for p in to_numbers if p and p.strip()))
    if not deduped:
        return []

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM", "")

    if not all([account_sid, auth_token, from_number]):
        err = "Twilio credentials not set — cannot send operational SMS"
        print(f"[notify] {err}")
        return [err]

    full_body = body.rstrip()
    if "Reply STOP" not in full_body:
        full_body = full_body + A2P_FOOTER
    if len(full_body) > MAX_MESSAGE_LENGTH:
        full_body = full_body[: MAX_MESSAGE_LENGTH - 3] + "..."

    client = Client(account_sid, auth_token)
    errors: List[str] = []
    for to_number in deduped:
        try:
            msg = client.messages.create(body=full_body, from_=from_number, to=to_number)
            print(f"[notify] Operational SMS sent to {to_number}. SID: {msg.sid}")
        except Exception as exc:
            err = f"Operational SMS failed for {to_number}: {exc}"
            errors.append(err)
            print(f"[notify] {err}")
    return errors


def send_sms(slots: List[Slot]) -> SendResult:
    if not slots:
        return SendResult([], [])

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM", "")

    if not all([account_sid, auth_token, from_number]):
        error = "Twilio credentials not set"
        print(f"[notify] {error} — printing alert instead:")
        print(_format_message(slots))
        return SendResult([], [error])

    client = Client(account_sid, auth_token)
    by_recipient = defaultdict(list)
    fallback_to = os.environ.get("TWILIO_TO", "")
    for slot in slots:
        recipient = slot.recipient_phone or fallback_to
        if recipient:
            by_recipient[recipient].append(slot)

    if not by_recipient:
        error = "No recipient phone configured"
        print(f"[notify] {error} — printing alert instead:")
        print(_format_message(slots))
        return SendResult([], [error])

    sent_slots: List[Slot] = []
    errors: List[str] = []
    for to_number, recipient_slots in by_recipient.items():
        body = _format_message(recipient_slots)
        if len(body) > MAX_MESSAGE_LENGTH:
            body = body[: MAX_MESSAGE_LENGTH - 3] + "..."
            print(f"[notify] Alert for {to_number} truncated to {MAX_MESSAGE_LENGTH} characters.")
        try:
            message = client.messages.create(body=body, from_=from_number, to=to_number)
            print(f"[notify] SMS sent to {to_number} ({len(recipient_slots)} slot(s)). SID: {message.sid}")
            sent_slots.extend(recipient_slots)
        except Exception as exc:
            error = f"SMS failed for {to_number}: {exc}"
            errors.append(error)
            print(f"[notify] {error}")
    return SendResult(sent_slots, errors)
