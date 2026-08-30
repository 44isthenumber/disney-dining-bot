"""Slice 1 dining-selection contract for public/index.html.

Guards combobox picker, Create Watch as the primary job, one party control,
watchable-only catalog rows, and shared isWatchable().
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "public" / "index.html").read_text(encoding="utf-8")


class DiningSelectionContractTest(unittest.TestCase):
    def test_is_watchable_helper(self):
        self.assertIn("function isWatchable(r)", INDEX)
        self.assertIn("filled(r.slug)", INDEX)
        self.assertIn("filled(r.booking_url)", INDEX)
        self.assertIn("function selectRestaurant(facilityId)", INDEX)
        self.assertIn("applyBookingTypeUI()", INDEX)

    def test_combobox_not_visible_native_select(self):
        self.assertIn('id="restaurant-combo-input"', INDEX)
        self.assertIn('id="restaurant-combo-list"', INDEX)
        self.assertIn('id="restaurant-select"', INDEX)
        self.assertIn("class=\"sr-only\"", INDEX)
        self.assertIn("role=\"combobox\"", INDEX)
        self.assertIn("ArrowDown", INDEX)
        self.assertIn("Escape", INDEX)

    def test_watch_this_and_see_dates(self):
        self.assertIn("Watch this", INDEX)
        self.assertIn("See dates", INDEX)
        self.assertNotIn("Check Calendar", INDEX)
        self.assertIn('data-action="watch-this"', INDEX)
        self.assertIn('data-action="see-dates"', INDEX)
        self.assertIn("selectRestaurant(btn.dataset.watchId)", INDEX)

    def test_default_tab_is_restaurants(self):
        self.assertIn('class="tab-btn active" data-tab="restaurants"', INDEX)
        self.assertIn('id="tab-restaurants" class="tab-panel active"', INDEX)
        self.assertIn('id="tab-watches" class="tab-panel"', INDEX)
        self.assertNotIn('class="tab-btn active" data-tab="watches"', INDEX)
        self.assertNotIn('id="tab-watches" class="tab-panel active"', INDEX)
        self.assertIn("No watches yet. Browse restaurants", INDEX)
        self.assertIn('id="goto-restaurants"', INDEX)
        self.assertIn('id="add-watch-btn"', INDEX)
        self.assertIn("function activateTab(name)", INDEX)
        rest = INDEX.find('id="tab-restaurants"')
        trip = INDEX.find('id="trip-bar"')
        create = INDEX.find('id="create-watch"')
        self.assertIn('aria-label="Trip start date"', INDEX)
        self.assertIn('aria-label="Trip end date"', INDEX)
        self.assertIn("else activateTab('restaurants')", INDEX)

    def test_one_party_control(self):
        self.assertNotIn("global-party", INDEX)
        self.assertIn("function getPartySize()", INDEX)
        self.assertIn("document.getElementById('party-size').value", INDEX)
        self.assertIn("disneyPartySize", INDEX)
        self.assertIn("localStorage.getItem('disneyPartySize') || '2'", INDEX)

    def test_park_chips_not_free_text_park_filter(self):
        self.assertIn('id="park-chips"', INDEX)
        self.assertIn("function renderParkChips()", INDEX)
        self.assertIn("All", INDEX)
        self.assertNotIn('id="park-filter"', INDEX)

    def test_catalog_incomplete_rows_fail_watchable_predicate(self):
        import json
        data = json.loads((ROOT / "restaurants.json").read_text(encoding="utf-8"))

        def is_watchable(r):
            def filled(v):
                return str(v or "").strip() != ""
            return (
                filled(r.get("facility_id"))
                and filled(r.get("name"))
                and filled(r.get("slug"))
                and filled(r.get("booking_url"))
            )

        skipped = {r["name"] for r in data["restaurants"] if not is_watchable(r)}
        self.assertIn("Hoop-Dee-Doo Musical Revue", skipped)
        self.assertIn("Celebration at the Top - Sip, Savor, Sparkle", skipped)
        harmony = next(r for r in data["restaurants"] if r["name"] == "Harmony Barber Shop")
        self.assertTrue(is_watchable(harmony))
        self.assertIn(".filter(isWatchable)", INDEX)
        self.assertIn("function watchableRestaurants()", INDEX)
        self.assertIn("watchableRestaurants()", INDEX)


if __name__ == "__main__":
    unittest.main()
