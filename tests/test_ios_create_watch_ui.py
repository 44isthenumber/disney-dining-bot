"""iOS Safari create-watch UI contract (date picker sheet + time window)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
MOBILE_CSS = INDEX.split("@media (max-width: 860px)", 1)[1].split("@media", 1)[0]


class IosCreateWatchUiContractTest(unittest.TestCase):
    def test_date_picker_overlay_and_fixed_footer(self):
        self.assertIn('id="date-picker-overlay"', INDEX)
        self.assertIn('class="date-picker-scroll"', INDEX)
        self.assertIn("function mountDatePickerOverlay()", INDEX)
        self.assertIn("function lockDatePickerScroll()", INDEX)
        self.assertIn("function commitDatePickerSelection()", INDEX)
        self.assertIn("function dismissDatePickerPreserveSelection()", INDEX)
        self.assertIn("#date-picker-panel.open .date-picker-actions", MOBILE_CSS)
        self.assertIn("position: fixed", MOBILE_CSS.split("#date-picker-panel.open .date-picker-actions", 1)[1][:400])
        self.assertIn("html.date-picker-modal-open", MOBILE_CSS)

    def test_dismiss_preserves_selection(self):
        backdrop = INDEX.split("date-picker-backdrop').addEventListener('click'", 1)[1][:350]
        self.assertIn("dismissDatePickerPreserveSelection()", backdrop)
        done = INDEX.split("date-picker-done').addEventListener('click'", 1)[1][:400]
        self.assertIn("dismissDatePickerPreserveSelection()", done)

    def test_signed_in_when_shows_meal_and_time_on_mobile(self):
        self.assertIn('id="when-meal-label"', INDEX)
        self.assertIn("html.has-session #meal-chips", MOBILE_CSS)
        self.assertIn("html.has-session .time-fields-wrap", MOBILE_CSS)
        self.assertIn("if (document.documentElement.classList.contains('has-session')) collapsed = false", INDEX)

    def test_guest_collapsed_still_hides_meal_not_signed_in(self):
        self.assertIn("html:not(.has-session) #create-watch.is-collapsed #meal-chips", INDEX)


if __name__ == "__main__":
    unittest.main()
