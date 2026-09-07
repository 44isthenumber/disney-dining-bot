"""Always-on WHO (party size) UI contract for public/index.html.

Guards Frame-locked order, chips 1-8, living caption, Done pulse,
collapsed visibility, and the guest submit expand path.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
FORM = INDEX.split('id="watch-form"', 1)[1].split("</form>", 1)[0]


class PartyWhoUiContractTest(unittest.TestCase):
    def test_order_where_when_who_cta(self):
        where = FORM.find('id="restaurant-combo"')
        when = FORM.find('id="toggle-date-picker"')
        who = FORM.find('id="who-step"')
        cta = FORM.find('id="create-btn"')
        self.assertGreater(where, -1)
        self.assertGreater(when, where)
        self.assertGreater(who, when)
        self.assertGreater(cta, who)
        where_body = FORM[FORM.find('id="restaurant-combo"') : FORM.find('id="toggle-date-picker"')]
        self.assertNotIn('id="party-size"', where_body)
        self.assertNotIn('id="party-chips"', where_body)

    def test_who_always_visible_when_collapsed(self):
        hide = re.search(
            r"#create-watch\.is-collapsed > h2.*?#create-watch\.is-collapsed #billing-next-banner \{ display: none !important; \}",
            INDEX,
            re.S,
        )
        self.assertIsNotNone(hide)
        block = hide.group(0)
        self.assertNotIn("who-step", block)
        self.assertNotIn("party-chips", block)
        self.assertNotIn("party-caption", block)
        self.assertNotIn(".party-row", block)
        self.assertIn("#meal-chips", block)
        self.assertIn(".create-step-contact", block)

    def test_default_party_two_and_chips_one_to_eight(self):
        self.assertIn('id="party-size"', FORM)
        self.assertIn('value="2"', FORM[FORM.find('id="party-size"') : FORM.find('id="party-size"') + 180])
        self.assertIn('id="party-caption"', FORM)
        self.assertIn("Party of 2", FORM)
        for n in range(1, 9):
            self.assertIn('data-party="%d"' % n, FORM)
        self.assertNotIn('data-party="9"', FORM)
        self.assertIn("PARTY_CHIP_MAX = 8", INDEX)
        self.assertIn('.party-chip[aria-checked="true"]', INDEX)
        self.assertIn("background: #000; color: #fff", INDEX)
        self.assertIn("#create-btn {\n    padding: 11px 24px; background: var(--ink);", INDEX)

    def test_living_caption_updates_with_selection(self):
        self.assertIn("caption.textContent = 'Party of ' + n", INDEX)
        self.assertIn("function syncPartyChips()", INDEX)
        self.assertIn("function setPartySize(", INDEX)
        self.assertIn("function bindPartyChips()", INDEX)

    def test_done_scrolls_and_pulses_who(self):
        self.assertIn("function pulseWhoStep()", INDEX)
        self.assertIn("who-gold-pulse", INDEX)
        self.assertIn("who-pulse", INDEX)
        self.assertIn("#aa8b54", INDEX)
        done = INDEX.split("date-picker-done').addEventListener('click'", 1)[1][:500]
        self.assertIn("pulseWhoStep()", done)
        self.assertNotIn("toggle-date-picker').scrollIntoView", done)
        self.assertIn("prefers-reduced-motion: reduce", INDEX)

    def test_dates_do_not_auto_expand_guest_starter(self):
        self.assertNotIn("hasRestaurant && hasDates", INDEX)
        collapsed_fn = INDEX.split("function guestStarterCollapsed()", 1)[1].split("function syncPartyChips", 1)[0]
        self.assertIn("guestStarterExpanded", collapsed_fn)
        self.assertNotIn("createDatePicker", collapsed_fn)
        self.assertIn(
            "if (isAnonymous()) return guestStarterCollapsed() ? 'Start my watch · from $4.99' : 'Start my watch · $4.99';",
            INDEX,
        )

    def test_collapsed_submit_expands_then_returns(self):
        submit = INDEX.split("watch-form').addEventListener('submit'", 1)[1]
        branch = submit.split("if (guestStarterCollapsed())", 1)[1].split("startGuestWatch()", 1)[0]
        self.assertIn("Choose a restaurant first.", branch)
        self.assertIn("Choose at least one date.", branch)
        self.assertIn("Enter your party size.", branch)
        self.assertIn("guestStarterExpanded = true", branch)
        self.assertIn("syncGuestStarter()", branch)
        self.assertIn("return;", branch)
        after_expand = branch.split("guestStarterExpanded = true", 1)[1]
        self.assertNotIn("startGuestWatch()", after_expand)

    def test_read_watch_form_validates_party(self):
        self.assertIn("if (!(partySize >= 1)) return { body: null, error: 'Enter your party size.' };", INDEX)

    def test_restaurant_max_disables_chips(self):
        apply = INDEX.split("function applyBookingTypeUI()", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("btn.disabled = v > maxParty", apply)
        self.assertIn("Math.min(maxPartyFor(r), PARTY_CHIP_MAX)", apply)
        self.assertIn("syncPartyChips()", apply)

    def test_party_persists_and_resets(self):
        self.assertIn("storageSet('disneyPartySize', this.value)", INDEX)
        self.assertIn("storageSet('disneyPartySize', String(n))", INDEX)
        self.assertIn("syncPartyChips()", INDEX)
        self.assertIn("setPartySize(body.party_size, false)", INDEX)

    def test_no_arsenal_bleed(self):
        who_css = INDEX.split(".create-step-who .who-box", 1)[1][:1800]
        self.assertNotIn("#ef0107", who_css.lower())
        self.assertNotIn("#063672", who_css.lower())
        self.assertIn("#aa8b54", INDEX)
        self.assertIn(".step-label {", INDEX)
        self.assertIn("color: #aa8b54", INDEX.split(".step-label {", 1)[1][:220])


if __name__ == "__main__":
    unittest.main()
