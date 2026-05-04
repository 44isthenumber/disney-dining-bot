import unittest

import disney_bot
import watch_store
from monitor import Slot
from notify import _format_message, booking_url


def make_slot(**overrides):
    data = {
        "restaurant_name": "'Ohana",
        "facility_id": "90002606",
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
        self.assertNotIn("Times:", message)

    def test_booking_url_includes_offer_id_and_slot_criteria(self):
        url = booking_url(make_slot(offer_id="abc 123", time="19:50"))
        self.assertIn("/dine-res/book/table-service/details/90002606/", url)
        self.assertIn("date=2026-07-01", url)
        self.assertIn("partySize=2", url)
        self.assertIn("time=19%3A50", url)
        self.assertIn("offerId=abc+123", url)

    def test_message_has_distinct_exact_booking_url_per_opening(self):
        message = _format_message([
            make_slot(time="19:50", label="07:50 PM", offer_id="offer-a"),
            make_slot(time="20:55", label="08:55 PM", offer_id="offer-b"),
        ])
        self.assertEqual(message.count("Book exact slot:"), 2)
        self.assertIn("time=19%3A50", message)
        self.assertIn("offerId=offer-a", message)
        self.assertIn("time=20%3A55", message)
        self.assertIn("offerId=offer-b", message)

    def test_watch_dates_expire_after_park_date_passes(self):
        self.assertFalse(watch_store.is_active_watch({"date": "2026-05-03"}, today="2026-05-04"))
        self.assertTrue(watch_store.is_active_watch({"date": "2026-05-04"}, today="2026-05-04"))
        self.assertTrue(watch_store.is_active_watch({"date": "2026-05-05"}, today="2026-05-04"))


if __name__ == "__main__":
    unittest.main()
