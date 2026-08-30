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
        self.assertIn("We monitor the openings.", INDEX)
        self.assertIn("We'll text you when your Walt Disney World reservations open up. You log in. You book.", INDEX)
        self.assertNotIn("The table is being watched.", INDEX)
        self.assertIn("We text you when a matching table newly opens.", INDEX)
        self.assertNotIn("SMS when a matching table newly opens.", INDEX)
        self.assertIn("New openings only", INDEX)
        self.assertIn("Text alerts", INDEX)
        self.assertIn("That's our job. We keep scanning so you don't have to.", INDEX)
        self.assertIn("Times that were already open stay quiet.", INDEX)
        self.assertNotIn("Continuously open times stay quiet.", INDEX)
        self.assertIn("New opening: California Grill", INDEX)
        self.assertNotIn("California Grill opened", INDEX)
        self.assertIn('id="how"', INDEX)
        self.assertIn('id="proof"', INDEX)
        self.assertIn('id="faq"', INDEX)
        self.assertIn('id="signin"', INDEX)
        self.assertIn("You select the restaurants and dining times you are interested in reserving.", INDEX)
        self.assertIn("We'll keep watch for those reservations to open.", INDEX)
        self.assertIn("We send you a text with the reservation link when it opens.", INDEX)
        self.assertNotIn("Create a precise watch", INDEX)
        self.assertIn("We scan frequently", INDEX)
        self.assertIn("Frequent scans", INDEX)
        self.assertIn("California Grill", INDEX)
        self.assertIn("Reply STOP to opt out", INDEX)
        self.assertIn("Reply HELP for help", INDEX)
        self.assertIn("Book:", INDEX)

    def test_production_auth_ids_not_mock_ids(self):
        for auth_id in (
            'id="login-overlay"',
            'id="login-profile"',
            'id="login-pwd"',
            'id="login-btn"',
            'id="login-error"',
        ):
            self.assertIn(auth_id, INDEX)
        self.assertIn('type="text" id="login-profile"', INDEX)
        self.assertNotIn('<select id="login-profile">', INDEX)
        self.assertIn('aria-label="Magic Table Finder"', INDEX)
        self.assertIn("text-align: left;", INDEX)
        self.assertIn("#login-overlay .l-btn-primary", INDEX)
        self.assertIn("color-scheme: light", INDEX)
        self.assertNotIn("For Craig and Jessica", INDEX)
        self.assertIn('<form class="signin-box">', INDEX)
        self.assertIn("closest('form')", INDEX)
        self.assertNotIn('id="login-form"', INDEX)
        self.assertNotIn("profile-select", INDEX)
        self.assertNotIn("password-input", INDEX)
        self.assertNotIn("signin-form", INDEX)
        self.assertNotIn("app.html", INDEX)
        self.assertNotIn("autofocus", INDEX.lower())
        self.assertNotRegex(INDEX, r'id="login-pwd"[^>]*value="')
        self.assertIn('id="login-email"', INDEX)
        self.assertIn('id="login-magic-btn"', INDEX)
        self.assertIn('id="login-magic-status"', INDEX)
        self.assertIn("Email a sign-in link", INDEX)
        self.assertIn("Private sign-in", INDEX)
        self.assertIn("signin=invalid", INDEX)
        self.assertIn("signin=ok", INDEX)
        self.assertIn("That sign-in link didn't complete", INDEX)
        self.assertIn("mtfSessionUser.kind === 'consumer'", INDEX)
        self.assertIn("signin=error", INDEX)
        self.assertIn("Sign-in is temporarily unavailable", INDEX)
        self.assertIn('id="billing-next-banner"', INDEX)
        self.assertIn('id="planner-checkout-btn"', INDEX)
        self.assertIn('id="billing-portal-btn"', INDEX)
        self.assertIn('id="upgrade-prompt"', INDEX)
        self.assertIn("Pay once for this watch", INDEX)
        self.assertIn("Pay and watch", INDEX)
        self.assertIn("function postWatch(body)", INDEX)
        self.assertIn("checkout_url", INDEX)
        self.assertIn("sms_consent: true", INDEX)
        self.assertIn("paid=ok", INDEX)
        self.assertIn("/billing/sync", INDEX)
        self.assertNotIn("$9", INDEX)
        self.assertNotIn("$19", INDEX)
        overlay = INDEX.split('id="login-overlay"', 1)[1].split('id="app-shell"', 1)[0]
        self.assertNotIn("For Craig and Jessica", overlay)
        self.assertNotIn('id="login-profile-list"', overlay)

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
        self.assertIn("You'll get a text when a matching table newly opens.", INDEX)
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
        self.assertNotIn("every 10 min", lowered)
        self.assertNotIn("every 10 minutes", lowered)
        self.assertNotIn("10-min", lowered)
        overlay = INDEX.split('id="login-overlay"', 1)[1].split('id="app-shell"', 1)[0]
        self.assertNotIn("SMS", overlay.replace("sms-consent.html", "").replace("sms-consent.html", ""))

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
            "Do I need to keep refreshing Disney?",
            "When do you ask for text consent?",
            "What if nothing opens?",
        ):
            self.assertIn(question, INDEX)
        self.assertIn("We do not guarantee a table will open.", INDEX)


if __name__ == "__main__":
    unittest.main()
