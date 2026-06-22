import base64
import json
import time
import unittest
from datetime import datetime, timedelta, timezone

import disney_bot
import monitor
import watch_store
from monitor import Slot
from notify import _format_message, booking_url


def make_slot(**overrides):
    data = {
        "restaurant_name": "'Ohana",
        "facility_id": "90002606",
        "slug": "ohana",
        "date": "2026-07-01",
        "time": "19:50",
        "label": "07:50 PM",
        "meal_period": "DINNER",
        "party_size": 2,
        "offer_id": "offer-123",
        "owner_id": "craig",
        "watch_id": "watch_abc",
        "recipient_phone": "whatsapp:+15555550123",
    }
    data.update(overrides)
    return Slot(**data)


def make_jwt(exp):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.signature"


def make_token_blob(access_token, refresh_token=""):
    payload = {"access_token": access_token, "refresh_token": refresh_token}
    return base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def make_signed_token_blob(access_token, refresh_token=""):
    payload = {"access_token": access_token, "refresh_token": refresh_token}
    blob = json.dumps(payload) + json.dumps({"kid": "guestcontroller", "alg": "ES256"})
    return "5=" + base64.urlsafe_b64encode(blob.encode()).decode().rstrip("=") + ".signature.extra"


class AlertSemanticsTest(unittest.TestCase):
    def test_filter_new_baselines_first_snapshot_without_alerting(self):
        slot = make_slot()
        original_load_open_keys = disney_bot._load_open_keys
        try:
            disney_bot._load_open_keys = lambda: None
            self.assertEqual(disney_bot.filter_new([slot], previous_open_keys=None), [])
        finally:
            disney_bot._load_open_keys = original_load_open_keys

    def test_filter_new_does_not_realert_still_open_slot(self):
        slot = make_slot()
        self.assertEqual(
            disney_bot.filter_new([slot], previous_open_keys={disney_bot._slot_key(slot)}),
            [],
        )

    def test_filter_new_returns_only_unseen_exact_slots(self):
        seen_slot = make_slot(time="19:50", label="07:50 PM", offer_id="offer-seen")
        new_slot = make_slot(time="20:55", label="08:55 PM", offer_id="offer-new")
        self.assertEqual(
            disney_bot.filter_new(
                [seen_slot, new_slot],
                previous_open_keys={disney_bot._slot_key(seen_slot)},
            ),
            [new_slot],
        )

    def test_filter_new_alerts_when_slot_reopens_after_being_absent(self):
        reopened_slot = make_slot(time="19:50", label="07:50 PM", offer_id="offer-new")
        previously_open_other_time = make_slot(time="20:55", label="08:55 PM", offer_id="offer-other")
        self.assertEqual(
            disney_bot.filter_new(
                [reopened_slot, previously_open_other_time],
                previous_open_keys={disney_bot._slot_key(previously_open_other_time)},
            ),
            [reopened_slot],
        )

    def test_offer_id_is_not_part_of_stable_slot_identity(self):
        old_offer = make_slot(time="19:50", label="07:50 PM", offer_id="offer-a")
        new_offer = make_slot(time="19:50", label="07:50 PM", offer_id="offer-b")
        self.assertEqual(
            disney_bot.filter_new([new_offer], previous_open_keys={disney_bot._slot_key(old_offer)}),
            [],
        )

    def test_failed_restaurant_poll_preserves_previous_open_keys(self):
        old_slot = make_slot()
        old_key = disney_bot._slot_key(old_slot)
        next_keys = disney_bot._next_open_keys(
            current_open_keys=set(),
            previous_open_keys={old_key},
            new_slots=[],
            sent_slots=[],
            failed_open_prefixes=[disney_bot._watch_open_prefix({
                "watch_id": old_slot.watch_id,
                "facility_id": old_slot.facility_id,
            })],
        )
        self.assertIn(old_key, next_keys)

    def test_failed_new_alert_is_not_baselined_until_sent(self):
        new_slot = make_slot()
        new_key = disney_bot._slot_key(new_slot)
        next_keys = disney_bot._next_open_keys(
            current_open_keys={new_key},
            previous_open_keys=set(),
            new_slots=[new_slot],
            sent_slots=[],
            failed_open_prefixes=[],
        )
        self.assertNotIn(new_key, next_keys)

    def test_sent_new_alert_is_baselined(self):
        new_slot = make_slot()
        new_key = disney_bot._slot_key(new_slot)
        next_keys = disney_bot._next_open_keys(
            current_open_keys={new_key},
            previous_open_keys=set(),
            new_slots=[new_slot],
            sent_slots=[new_slot],
            failed_open_prefixes=[],
        )
        self.assertIn(new_key, next_keys)

    def test_message_lists_each_new_opening_not_all_times_grouped(self):
        message = _format_message([
            make_slot(time="19:50", label="07:50 PM", offer_id="offer-a"),
            make_slot(time="20:55", label="08:55 PM", offer_id="offer-b"),
        ])
        self.assertIn("2 new openings", message)
        self.assertIn("New opening: 'Ohana", message)
        self.assertIn("2026-07-01 at 07:50 PM", message)
        self.assertIn("2026-07-01 at 08:55 PM", message)
        self.assertIn("Reply STOP to opt out. Reply HELP for help.", message)
        self.assertNotIn("Times:", message)

    def test_booking_url_uses_restaurant_slug_with_no_query_params(self):
        # Disney's SPA does not honor date/time/partySize/offerId on a cold
        # URL load, so we link to the canonical restaurant page (same URL the
        # bot itself navigates to before polling) and rely on the message body
        # to carry the slot details.
        url = booking_url(make_slot(offer_id="abc 123", time="19:50"))
        self.assertEqual(url, "https://disneyworld.disney.go.com/dine-res/restaurant/ohana/")
        self.assertNotIn("offerId", url)
        self.assertNotIn("?", url)

    def test_booking_url_falls_back_to_facility_id_when_slug_missing(self):
        url = booking_url(make_slot(slug=""))
        self.assertEqual(url, "https://disneyworld.disney.go.com/dine-res/restaurant/90002606/")

    def test_message_lists_each_opening_distinctly(self):
        message = _format_message([
            make_slot(time="19:50", label="07:50 PM", offer_id="offer-a"),
            make_slot(time="20:55", label="08:55 PM", offer_id="offer-b"),
        ])
        # Two openings → two "Book:" lines and two distinct time labels in the
        # body, even though the URL is the same per restaurant per day.
        self.assertEqual(message.count("Book:"), 2)
        self.assertIn("07:50 PM", message)
        self.assertIn("08:55 PM", message)

    def test_watch_dates_expire_after_park_date_passes(self):
        self.assertFalse(watch_store.is_active_watch({"date": "2026-05-03"}, today="2026-05-04"))
        self.assertTrue(watch_store.is_active_watch({"date": "2026-05-04"}, today="2026-05-04"))
        self.assertTrue(watch_store.is_active_watch({"date": "2026-05-05"}, today="2026-05-04"))

    def test_disney_cookie_token_valid_after_more_than_24_hours(self):
        token = make_jwt(int(time.time()) + 172800)
        bearer = monitor._bearer_from_cookie_value(make_token_blob(token))
        self.assertEqual(bearer, f"BEARER {token}")

    def test_disney_cookie_token_with_expired_access_and_refresh_is_refreshable(self):
        token = make_jwt(int(time.time()) - 60)
        state = monitor._token_state_from_cookie_value(make_token_blob(token, "refresh-token"))
        self.assertEqual(state.access_token, token)
        self.assertEqual(state.refresh_token, "refresh-token")
        self.assertLess(state.expires_at, time.time())

    def test_disney_cookie_token_accepts_signed_base64url_wrapper(self):
        token = make_jwt(int(time.time()) + 172800)
        state = monitor._token_state_from_cookie_value(make_signed_token_blob(token, "refresh-token"))
        self.assertEqual(state.access_token, token)
        self.assertEqual(state.refresh_token, "refresh-token")
        self.assertGreater(state.expires_at, time.time())

    def test_disney_auth_errors_are_categorized(self):
        self.assertEqual(disney_bot._error_category(monitor.DisneyAuthRequired("login required")), "disney_auth")
        self.assertEqual(disney_bot._error_category("No Disney auth token found in Playwright profile"), "disney_auth")

    # ── session-failure alert grace window ──────────────────────────────────

    def test_consecutive_auth_failures_increments_and_resets(self):
        self.assertEqual(disney_bot._next_consecutive_auth_failures(0, True), 1)
        self.assertEqual(disney_bot._next_consecutive_auth_failures(2, True), 3)
        # Any clean poll resets the streak.
        self.assertEqual(disney_bot._next_consecutive_auth_failures(5, False), 0)
        # Missing / malformed prior state is treated as 0.
        self.assertEqual(disney_bot._next_consecutive_auth_failures(None, True), 1)
        self.assertEqual(disney_bot._next_consecutive_auth_failures("bad", True), 1)

    def test_no_alert_during_grace_window(self):
        now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(disney_bot._should_send_session_alert(1, None, now))
        self.assertFalse(disney_bot._should_send_session_alert(2, None, now))

    def test_alert_fires_at_threshold(self):
        now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(disney_bot._should_send_session_alert(3, None, now))

    def test_recovery_failure_alone_does_not_alert(self):
        # The core bug fix: alerting is driven by the consecutive-failure count,
        # not by recovery returning False. A single failed poll must stay silent.
        now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(disney_bot._should_send_session_alert(1, None, now))

    def test_no_realert_within_6h(self):
        now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        last_alert = (now - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        self.assertFalse(disney_bot._should_send_session_alert(4, last_alert, now))

    def test_realert_after_6h(self):
        now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        last_alert = (now - timedelta(hours=7)).isoformat().replace("+00:00", "Z")
        self.assertTrue(disney_bot._should_send_session_alert(4, last_alert, now))

    def test_clean_poll_rearms_alerting(self):
        # Option B: a clean poll resets the streak to 0 AND the caller clears
        # last_alert_at. A fresh outage then reaching threshold pages again even
        # though the wall-clock is well within the prior alert's 6h cooldown.
        now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(disney_bot._next_consecutive_auth_failures(4, False), 0)
        self.assertTrue(disney_bot._should_send_session_alert(3, None, now))

    def test_naive_now_is_handled(self):
        # poll() passes datetime.now(timezone.utc) (aware), but guard against a
        # naive `now` so the timedelta comparison never raises.
        now = datetime(2026, 6, 22, 12, 0)
        last_alert = "2026-06-22T04:00:00Z"
        self.assertTrue(disney_bot._should_send_session_alert(3, last_alert, now))


if __name__ == "__main__":
    unittest.main()
