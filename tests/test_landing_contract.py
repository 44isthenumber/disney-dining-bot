"""Quiet Luxury landing contract for public/index.html.

Guards the production SPA restyle: visual tokens, locked IA, real auth IDs,
and no mock / ops jargon leaking into the UI.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "public" / "index.html").read_text(encoding="utf-8")


class LandingContractTest(unittest.TestCase):
    def test_quiet_luxury_tokens_and_type(self):
        self.assertIn("Fraunces", INDEX)
        self.assertIn("Source Sans 3", INDEX)
        self.assertIn("--ink: #1c1917", INDEX)
        self.assertIn("--paper: #f6f1e8", INDEX)
        self.assertIn("--gold: #b0894a", INDEX)
        self.assertIn("--moss: #3f5c4a", INDEX)
        self.assertIn("--blue: #1a56db", INDEX)

    def test_locked_promise_and_headline(self):
        self.assertIn("The table is being watched.", INDEX)
        self.assertIn("SMS when a matching table newly opens.", INDEX)
        self.assertIn('id="how"', INDEX)
        self.assertIn('id="proof"', INDEX)
        self.assertIn('id="faq"', INDEX)
        self.assertIn('id="signin"', INDEX)
        self.assertIn("Create a precise watch", INDEX)
        self.assertIn("We check every 10 minutes", INDEX)
        self.assertIn("SMS only when a matching time newly opens", INDEX)
        self.assertIn("California Grill", INDEX)
        self.assertIn("Reply STOP to opt out", INDEX)
        self.assertIn("Reply HELP for help", INDEX)

    def test_production_auth_ids_not_mock_ids(self):
        for auth_id in (
            'id="login-overlay"',
            'id="login-profile"',
            'id="login-pwd"',
            'id="login-btn"',
            'id="login-error"',
            'id="login-form"',
        ):
            self.assertIn(auth_id, INDEX)
        self.assertNotIn("profile-select", INDEX)
        self.assertNotIn("password-input", INDEX)
        self.assertNotIn("signin-form", INDEX)
        self.assertNotIn("app.html", INDEX)
        self.assertNotIn("autofocus", INDEX.lower())
        self.assertNotRegex(INDEX, r'id="login-pwd"[^>]*value="')

    def test_overlay_is_scrollable_landing_not_flex_box(self):
        overlay_css = re.search(
            r"#login-overlay \{\s*position: fixed;[^}]+\}",
            INDEX,
        )
        self.assertIsNotNone(overlay_css)
        block = overlay_css.group(0)
        self.assertIn("overflow-y: auto", block)
        self.assertIn("display: block", block)
        self.assertNotIn("display: flex", block)

    def test_legal_urls_are_relative(self):
        self.assertIn('href="/privacy.html"', INDEX)
        self.assertIn('href="/terms.html"', INDEX)
        self.assertIn('href="/sms-consent.html"', INDEX)

    def test_empty_watch_and_create_copy(self):
        self.assertIn("No watches yet. Create one above.", INDEX)
        self.assertIn("You'll get an SMS when a matching table newly opens.", INDEX)
        self.assertNotIn("calendar is optional", INDEX.lower())

    def test_no_forbidden_copy(self):
        lowered = INDEX.lower()
        self.assertNotIn("re-seed on vps", lowered)
        self.assertNotIn("worker may be stalled", lowered)
        self.assertNotIn("worker issue", lowered)
        self.assertNotIn("the method", lowered)
        self.assertNotIn("bespoke", lowered)
        self.assertNotIn("battery remain", lowered)
        self.assertNotIn("alert semantics", lowered)
        self.assertNotIn("🏰", INDEX)

    def test_primary_ctas_are_ink(self):
        for selector in ("#login-btn", "#create-btn", "#toggle-date-picker", "#date-picker-done"):
            self.assertIn(selector, INDEX)
        self.assertIn("#create-btn {\n    padding: 11px 24px; background: var(--ink);", INDEX)
        self.assertIn("#toggle-date-picker {\n    display: block;", INDEX)
        self.assertIn("background: var(--ink); color: var(--paper);", INDEX)

    def test_login_js_does_not_steal_focus_on_first_paint(self):
        self.assertIn("function showLogin(opts)", INDEX)
        self.assertIn("scrollToSignin", INDEX)
        self.assertIn("landing-nav", INDEX)
        self.assertIn("landing-open", INDEX)
        self.assertNotIn(
            "setTimeout(function() { document.getElementById('login-pwd').focus(); }, 50);",
            INDEX,
        )

    def test_faq_six_questions(self):
        for question in (
            "Do you text every open table?",
            "Whose phone gets the alert?",
            "Is this an official Disney product?",
            "How often do you check?",
            "When do you ask for SMS consent?",
            "What if nothing opens?",
        ):
            self.assertIn(question, INDEX)
        self.assertIn("We do not guarantee a table will open.", INDEX)


if __name__ == "__main__":
    unittest.main()
