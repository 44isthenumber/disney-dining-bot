"""iOS Safari create-watch UI contract (date picker sheet + time window)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
MOBILE_CSS = INDEX.split("@media (max-width: 860px)", 1)[1].split("@media", 1)[0]


class IosCreateWatchUiContractTest(unittest.TestCase):
    def test_date_picker_fixed_footer_not_sticky_in_scroll(self):
        self.assertIn('class="date-picker-scroll"', INDEX)
        self.assertIn("function closeCreateDatePicker()", INDEX)
        self.assertIn("function openCreateDatePicker()", INDEX)
        self.assertIn('id="date-picker-backdrop"', INDEX)
        self.assertIn("#date-picker-panel.open { display: flex; }", MOBILE_CSS)
        self.assertIn(".date-picker-scroll", MOBILE_CSS)
        self.assertIn("flex: 0 0 auto", MOBILE_CSS)
        self.assertIn("position: relative; bottom: auto", MOBILE_CSS)
        self.assertNotIn("padding-bottom: env(safe-area-inset-bottom)", MOBILE_CSS)

    def test_done_closes_via_shared_helper(self):
        done = INDEX.split("date-picker-done').addEventListener('click'", 1)[1][:400]
        self.assertIn("closeCreateDatePicker()", done)
        self.assertNotIn("classList.remove('open')", done)

    def test_mobile_time_window_visible_without_disclosure(self):
        self.assertIn('id="time-window-label"', INDEX)
        self.assertIn("Optional time window", INDEX)
        self.assertIn("function syncTimeFieldsForViewport()", INDEX)
        self.assertIn("#time-toggle { display: none; }", MOBILE_CSS)
        self.assertIn("#time-fields[hidden] { display: grid !important; }", MOBILE_CSS)
        self.assertIn("min-height: 44px", MOBILE_CSS)

    def test_desktop_keeps_time_disclosure(self):
        self.assertIn('id="time-toggle"', INDEX)
        self.assertIn("Only certain times?", INDEX)
        self.assertNotIn("#time-toggle { display: none; }", INDEX.split("@media (max-width: 860px)", 1)[0])


if __name__ == "__main__":
    unittest.main()
