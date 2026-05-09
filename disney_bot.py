"""Self-hosted Disney dining monitor worker.

Usage:
    python disney_bot.py           # start polling loop
    python disney_bot.py --once    # single poll then exit
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from typing import Dict, List, Optional

import schedule
import yaml
from dotenv import load_dotenv

import storage
import watch_store
from monitor import DisneyAuthRequired, Slot, check_slots_for_restaurant
from notify import send_operational_sms, send_sms
import os
import subprocess

load_dotenv()

OPEN_SLOTS_FILE = "open_slots.json"


RECOVERY_LOG_PATH = os.environ.get(
    "DISNEY_RECOVERY_LOG_PATH",
    "/var/log/disney-dining-bot/last-recovery.log",
)


def _write_recovery_log(stdout: str, stderr: str, returncode: int) -> None:
    """Persist the full seed_disney_session.py output for post-mortem.

    Falls back to project root if the configured path isn't writable (e.g.
    local dev without /var/log access). Best-effort; never raises.
    """
    candidates = [RECOVERY_LOG_PATH]
    fallback = os.path.join(
        os.path.dirname(os.path.abspath(__file__)) or ".", "last-recovery.log"
    )
    if fallback not in candidates:
        candidates.append(fallback)
    body = (
        f"=== seed_disney_session.py recovery attempt @ {datetime.now(timezone.utc).isoformat()} ===\n"
        f"exit_code: {returncode}\n"
        f"--- stdout ---\n{stdout or ''}\n"
        f"--- stderr ---\n{stderr or ''}\n"
    )
    for path in candidates:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as fh:
                fh.write(body)
            return
        except Exception:
            continue


def attempt_disney_session_recovery() -> bool:
    """Attempt to automatically re-seed the Disney session using dedicated bot credentials.

    Returns True if recovery was successful (or not needed), False if manual intervention is required.
    """
    email = os.environ.get("DISNEY_LOGIN_EMAIL", "").strip()
    password = os.environ.get("DISNEY_LOGIN_PASSWORD", "").strip()

    if not email or not password:
        print("[recovery] No DISNEY_LOGIN_EMAIL / DISNEY_LOGIN_PASSWORD set — cannot auto-recover.")
        return False

    print("[recovery] Attempting automatic Disney session recovery...")

    try:
        # Run the seeder *headed* under the xvfb display the systemd service
        # already provides. Truly headless Chromium (--headless=new) is detected
        # by Akamai on disneyworld.disney.go.com and aborted with
        # ERR_HTTP2_PROTOCOL_ERROR before any page renders. The worker poll
        # itself runs headed-under-xvfb (DISNEY_HEADLESS=false in .env) and
        # navigates fine; matching that mode lets recovery succeed.
        env = os.environ.copy()
        env["DISNEY_HEADLESS"] = "false"

        result = subprocess.run(
            [sys.executable, "seed_disney_session.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

        _write_recovery_log(result.stdout, result.stderr, result.returncode)

        if result.returncode == 0:
            print("[recovery] Session recovery successful.")
            return True
        else:
            tail_out = (result.stdout or "")[-400:]
            tail_err = (result.stderr or "")[-400:]
            print(
                f"[recovery] Recovery failed (exit {result.returncode}). "
                f"Full log: {RECOVERY_LOG_PATH}. "
                f"stdout tail: {tail_out!r} stderr tail: {tail_err!r}"
            )
            return False

    except Exception as exc:
        print(f"[recovery] Recovery attempt crashed: {exc}")
        return False


def _configured_owner_phones() -> list:
    """Return distinct E.164/whatsapp phone numbers across all configured owners."""
    phones = []
    seen = set()
    for user in watch_store.profiles(include_private=True).values():
        phone = (user.get("phone") or "").strip()
        if phone and phone not in seen:
            seen.add(phone)
            phones.append(phone)
    return phones


def send_session_expired_alert(owner_phones: list[str]) -> None:
    """Alert owners that the Disney session needs manual attention (Twilio A2P)."""
    if not owner_phones:
        print("[notify] No phones configured for session alert.")
        return

    message = (
        "Disney Dining Bot: Disney login session failed after automatic recovery.\n"
        "Manual re-seed required. On a machine with your SSH key:\n"
        "ssh -i ~/.ssh/disney_dining_vps -t root@107.170.35.91 "
        "'cd /opt/disney-dining-bot && . .venv/bin/activate && "
        "DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py'"
    )

    errors = send_operational_sms(owner_phones, message)
    for err in errors:
        print(f"[notify] {err}")



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
        slot.meal_period.upper(),
        str(slot.party_size),
    ])


def _watch_open_prefix(watch: dict) -> str:
    return "__".join([
        str(watch.get("watch_id") or watch.get("owner_id") or "unknown"),
        str(watch.get("facility_id") or ""),
        "",
    ])


def _load_seen() -> Dict[str, str]:
    data = storage.read_json("seen_slots.json") or {}
    if isinstance(data, dict) and isinstance(data.get("slots"), dict):
        return data["slots"]
    if isinstance(data, dict):
        return data
    return {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _error_category(exc_or_message) -> str:
    if isinstance(exc_or_message, DisneyAuthRequired):
        return "disney_auth"
    message = str(exc_or_message).lower()
    if "disney auth required" in message or "no disney auth token" in message or "disney returned 401" in message:
        return "disney_auth"
    if "akamai" in message or "http 428" in message or "http 403" in message:
        return "akamai"
    if "sms failed" in message or "twilio" in message or "recipient phone" in message:
        return "notification"
    if "timeout" in message or "connection" in message or "network" in message:
        return "network"
    return "unknown"


def _save_seen(seen: Dict[str, str]) -> None:
    storage.write_json("seen_slots.json", {
        "schema_version": 1,
        "updated_at": _utc_now().isoformat() + "Z",
        "slots": seen,
    })


def _load_open_keys() -> Optional[set]:
    data = storage.read_json(OPEN_SLOTS_FILE)
    if not isinstance(data, dict):
        return None
    slots = data.get("slots")
    if not isinstance(slots, list):
        return None
    return {str(slot) for slot in slots}


def _save_open_keys(keys: set) -> None:
    storage.write_json(OPEN_SLOTS_FILE, {
        "schema_version": 1,
        "updated_at": _utc_now().isoformat() + "Z",
        "slots": sorted(keys),
    })


def filter_new(slots: List[Slot], previous_open_keys: Optional[set] = None) -> List[Slot]:
    """Return exact slots that opened since the previous poll.

    If there is no previous open-slot snapshot, baseline the current state
    without alerting. That prevents a deploy/restart from sending every slot
    Disney already had open.
    """
    if previous_open_keys is None:
        previous_open_keys = _load_open_keys()
    if previous_open_keys is None:
        return []

    new = []
    for s in slots:
        if _slot_key(s) not in previous_open_keys:
            new.append(s)
    return new


def _next_open_keys(
    current_open_keys: set,
    previous_open_keys: Optional[set],
    new_slots: List[Slot],
    sent_slots: List[Slot],
    failed_open_prefixes: List[str],
) -> set:
    sent_keys = {_slot_key(slot) for slot in sent_slots}
    new_keys = {_slot_key(slot) for slot in new_slots}
    next_open_keys = current_open_keys - (new_keys - sent_keys)
    if previous_open_keys and failed_open_prefixes:
        for key in previous_open_keys:
            if any(key.startswith(prefix) for prefix in failed_open_prefixes):
                next_open_keys.add(key)
    return next_open_keys


def mark_seen(slots: List[Slot]) -> None:
    if not slots:
        return
    seen = _load_seen()
    now = _utc_now().isoformat() + "Z"
    for slot in slots:
        seen[_slot_key(slot)] = now
    _save_seen(seen)


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
            target_meals = {m.upper() for m in (watch.get("meal_periods") or ["ALL"])}
            if "ALL" not in target_meals and slot.meal_period.upper() not in target_meals:
                continue
            if watch.get("time_from") and slot.time < watch["time_from"]:
                continue
            if watch.get("time_to") and slot.time > watch["time_to"]:
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
    state_at_start = storage.read_json("bot_state.json") or {}
    watches = watch_store.load_watches()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    grouped = watch_store.grouped_restaurant_requests(watches)
    print(f"\n[{ts}] Polling {len(watches)} watch(es) across {len(grouped)} restaurant request(s) …")

    all_slots: List[Slot] = []
    errors = []
    failed_open_prefixes = []
    did_send_session_manual_alert = False
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
            errors.append({"restaurant": name, "category": _error_category(e), "error": str(e)})
            failed_open_prefixes.extend(_watch_open_prefix(watch) for watch in restaurant.get("watches", []))
            print(f"[bot] Check failed for {name}: {e}")

    # === Disney Session Recovery (Login Agent) ===
    auth_failed = any(error.get("category") == "disney_auth" for error in errors)
    login_agent_triggered = False
    if auth_failed:
        # Cooldown: at most once per ~9 minutes so the 10-minute systemd timer
        # never has a guaranteed silent-failure cycle. Previous 15-min cooldown
        # blocked half of all polls from even attempting recovery.
        last_attempt = state_at_start.get("last_login_agent_attempt_at")
        cooldown_minutes = 9
        can_attempt = True
        if last_attempt:
            try:
                parsed = datetime.fromisoformat(last_attempt.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - parsed < timedelta(minutes=cooldown_minutes):
                    can_attempt = False
                    print(f"[bot] Login Agent on cooldown (last attempt {last_attempt}). Skipping recovery this cycle.")
            except Exception:
                pass

        if can_attempt:
            print("[bot] Disney auth error detected — activating Login Agent...")
            login_agent_triggered = True
            recovered = attempt_disney_session_recovery()
            if recovered:
                print("[bot] Login Agent succeeded — retrying failed restaurants...")
                errors = []
                all_slots = []
                failed_open_prefixes = []
                for restaurant in grouped:
                    name = restaurant.get("name", "?")
                    try:
                        slots = check_slots_for_restaurant(restaurant)
                        owner_slots = _matching_owner_slots(slots, restaurant.get("watches", []))
                        all_slots.extend(owner_slots)
                    except Exception as e:
                        errors.append({"restaurant": name, "category": _error_category(e), "error": str(e)})
                        print(f"[bot] Retry failed for {name}: {e}")
                auth_failed = any(error.get("category") == "disney_auth" for error in errors)
            else:
                print("[bot] Login Agent failed this cycle.")
                # SMS owners that manual re-seed is required, rate-limited to
                # once per 6 hours so a stuck session doesn't flood Twilio.
                last_alert = state_at_start.get("last_session_manual_alert_at")
                should_alert = True
                if last_alert:
                    try:
                        parsed_alert = datetime.fromisoformat(last_alert.replace("Z", "+00:00"))
                        if parsed_alert.tzinfo is None:
                            parsed_alert = parsed_alert.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) - parsed_alert < timedelta(hours=6):
                            should_alert = False
                    except Exception:
                        pass
                if should_alert:
                    phones = _configured_owner_phones()
                    if phones:
                        print(f"[bot] Sending session-expired alert to {len(phones)} owner(s).")
                        try:
                            send_session_expired_alert(phones)
                            did_send_session_manual_alert = True
                        except Exception as exc:
                            print(f"[bot] Session-expired alert dispatch crashed: {exc}")
                    else:
                        print("[bot] Recovery failed but no owner phones are configured for alerting.")
        else:
            print("[bot] Skipping Login Agent due to cooldown.")

    previous_open_keys = _load_open_keys()
    current_open_keys = {_slot_key(slot) for slot in all_slots}
    new_slots = filter_new(all_slots, previous_open_keys)
    sms_sent = False
    sent_slots: List[Slot] = []
    if new_slots:
        print(f"[bot] Sending alert for {len(new_slots)} new slot(s).")
        try:
            send_result = send_sms(new_slots)
            sent_slots = send_result.sent_slots
            sms_sent = bool(sent_slots)
            for error in send_result.errors:
                errors.append({"restaurant": "notification", "category": _error_category(error), "error": error})
        except Exception as e:
            errors.append({"restaurant": "notification", "category": _error_category(e), "error": str(e)})
            print(f"[bot] Notification failed: {e}")
        if sms_sent:
            mark_seen(sent_slots)
    else:
        if previous_open_keys is None and current_open_keys:
            print(f"[bot] Baselined {len(current_open_keys)} currently open slot(s); future changes will alert.")
        else:
            print("[bot] No newly opened slots to alert on.")

    _save_open_keys(_next_open_keys(
        current_open_keys,
        previous_open_keys,
        new_slots,
        sent_slots,
        failed_open_prefixes,
    ))

    now_utc = _utc_now().isoformat() + "Z"
    previous_state = state_at_start
    auth_status = "reauth_required" if auth_failed else "ok"
    storage.write_json("bot_state.json", {
        "last_poll_at": now_utc,
        "last_successful_poll_at": now_utc if not errors else previous_state.get("last_successful_poll_at"),
        "slots_found_last_poll": len(new_slots),
        "watch_count": len(watches),
        "restaurant_request_count": len(grouped),
        "last_errors": errors,
        "auth_status": auth_status,
        "auth_required_since": (
            previous_state.get("auth_required_since") if auth_failed and previous_state.get("auth_status") == "reauth_required"
            else now_utc if auth_failed
            else None
        ),
        "last_auth_ok_at": now_utc if not auth_failed else previous_state.get("last_auth_ok_at"),
        "last_login_agent_attempt_at": (
            now_utc if login_agent_triggered else previous_state.get("last_login_agent_attempt_at")
        ),
        "last_session_manual_alert_at": (
            now_utc if did_send_session_manual_alert else previous_state.get("last_session_manual_alert_at")
        ),
        "session_status": "needs_attention" if errors else "ok",
        "last_sms_sent_at": now_utc if sms_sent else previous_state.get("last_sms_sent_at"),
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
