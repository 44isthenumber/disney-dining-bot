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
        overlay, _, rest = INDEX.partition('id="app-shell"')
        self.assertIn('h1 class="brand-wordmark"', rest)
        self.assertIn('class="wordmark-wand-accent"', overlay)
        self.assertIn('class="wordmark-wand-accent"', rest)
        self.assertIn("wordmark-magic", overlay)
        self.assertIn("wordmark-magic", rest)
        self.assertEqual(INDEX.count('class="wordmark-wand-accent"'), 2)
        self.assertIn('viewBox="0 0 48 48"', INDEX)
        self.assertIn('stroke-width="3.2"', INDEX)
        self.assertIn(".wordmark-wand-accent", INDEX)
        self.assertIn("height: 2.15em", INDEX)
        self.assertIn("left: -1.08em", INDEX)
        shaft = re.search(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"[^>]*stroke-width="3.2"', INDEX)
        self.assertIsNotNone(shaft)
        self.assertLessEqual(max(float(shaft.group(1)), float(shaft.group(3))), 24.0)
        on_letter = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="currentColor"/>', INDEX)
        dust_on_m = [c for c in on_letter if float(c[0]) >= 26.0]
        self.assertGreaterEqual(len(dust_on_m), 8)
        self.assertNotIn('class="wordmark-mark"', INDEX)
        self.assertNotIn("logoWandGlow", INDEX)
        self.assertNotIn('width="88"', INDEX)
        self.assertNotIn('viewBox="0 0 180 126"', INDEX)
        self.assertNotIn(".landing-wordmark span.wordmark-name { display: none; }", INDEX)
        self.assertNotIn("filter: drop-shadow", INDEX)
        self.assertIn("@media (max-width: 640px)", INDEX)
        self.assertIn(".landing-wordmark { font-size: 16px; }", INDEX)
        self.assertIn("#app-shell > header", INDEX)
        self.assertIn("overflow: visible", INDEX.split("#app-shell > header", 1)[1][:400])
        self.assertNotIn("🏰", INDEX)
        self.assertNotIn("Mickey", INDEX)
        self.assertNotIn("Tinker Bell", INDEX)
        self.assertNotIn("Cinderella", INDEX)

    def test_hero_wand_is_the_only_fireworks(self):
        self.assertIn('class="hero-wand"', INDEX)
        self.assertIn('class="hero-wand-svg"', INDEX)
        self.assertIn('viewBox="0 0 900 380"', INDEX)
        self.assertIn("min(920px", INDEX)
        self.assertIn("@keyframes hero-dust-a", INDEX)
        self.assertIn("@keyframes hero-dust-b", INDEX)
        self.assertIn("@keyframes hero-dust-c", INDEX)
        still = ".hero-wand .dust-a, .hero-wand .dust-b, .hero-wand .dust-c { animation: none; }"
        self.assertIn(still, INDEX)
        self.assertGreater(INDEX.rfind(still), INDEX.find("@keyframes hero-dust-c"))
        self.assertNotIn("plate-motif", INDEX)
        self.assertNotIn("candleGlow", INDEX)
        self.assertNotIn('class="l-plate"', INDEX)
        overlay, _, rest = INDEX.partition('id="app-shell"')
        self.assertIn('class="hero-wand"', overlay)
        self.assertNotIn('class="hero-wand"', rest)
        self.assertNotIn("animation:", INDEX.split(".wordmark-wand-accent {", 1)[1][:400])
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
        self.assertIn('id="private-signin-toggle"', INDEX)
        self.assertIn('id="private-signin" hidden', INDEX)
        self.assertIn('id="phone-setup"', INDEX)
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
        self.assertIn("Pay $4.99 for this watch", INDEX)
        self.assertIn("Pay $4.99 and watch", INDEX)
        self.assertNotIn("Pay once for this watch", INDEX)
        self.assertIn("function postWatch(body)", INDEX)
        self.assertEqual(INDEX.count("async function postWatch(body)"), 1)
        self.assertIn("checkout_url", INDEX)
        self.assertIn("sms_consent: true", INDEX)
        self.assertIn("paid=ok", INDEX)
        self.assertIn("/billing/sync", INDEX)
        self.assertIn("!syncRes.ok", INDEX)
        self.assertNotIn("$9", INDEX)
        self.assertNotIn("$19", INDEX)
        self.assertIn("$4.99", INDEX)
        self.assertIn("$14.99", INDEX)
        self.assertIn('id="pricing"', INDEX)
        self.assertIn("Simple pricing", INDEX)
        self.assertIn('id="plan-line"', INDEX)
        self.assertNotIn('id="trip-bar"', INDEX)
        self.assertIn('id="modal-phone"', INDEX)
        self.assertIn(">Sign out<", INDEX)
        self.assertNotIn(">Lock<", INDEX)
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
        self.assertNotIn("No watches yet. Browse restaurants", INDEX)
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

    def test_faq_has_horizontal_gutter(self):
        self.assertIn(".l-faq { width: min(720px, calc(100% - 48px)); margin: 0 auto; }", INDEX)
        self.assertNotRegex(INDEX, r"\.l-faq \{ max-width: 720px; margin: 0 auto; \}")

    def test_faq_includes_cost(self):
        for question in (
            "Do you text every open table?",
            "Whose phone gets the alert?",
            "Is this an official Disney product?",
            "Do I need to keep refreshing Disney?",
            "When do you ask for text consent?",
            "What if nothing opens?",
            "How much does it cost?",
        ):
            self.assertIn(question, INDEX)
        self.assertIn("We do not guarantee a table will open.", INDEX)
        self.assertIn("Single Watch is $4.99 one-time.", INDEX)

    def test_guest_watch_builder_landing(self):
        self.assertIn('id="landing-watch-slot"', INDEX)
        self.assertIn('id="create-watch-home"', INDEX)
        self.assertIn("function placeCreateWatch(", INDEX)
        self.assertIn("function isAnonymous()", INDEX)
        self.assertIn("/restaurants.json", INDEX)
        self.assertIn("mtfWatchDraft", INDEX)
        self.assertIn("function resumeWatchDraft(", INDEX)
        self.assertIn("function startGuestWatch()", INDEX)
        self.assertIn('id="guest-email"', INDEX)
        self.assertIn("Continue to payment · $4.99", INDEX)
        self.assertIn("Already have watches?", INDEX)
        hero = INDEX.split('class="l-hero"', 1)[1].split('id="how"', 1)[0]
        self.assertNotIn('class="l-hero-actions"', hero)

    def test_pop_restyle_material_layer(self):
        self.assertIn('<meta name="theme-color" content="#f6f1e8"', INDEX)
        self.assertIn("--shadow-1:", INDEX)
        self.assertIn("--shadow-2:", INDEX)
        self.assertIn("--shadow-3:", INDEX)
        self.assertIn("--hairline:", INDEX)
        self.assertIn("feTurbulence", INDEX)
        grain = INDEX.split("body::before {", 1)[1][:700]
        self.assertIn("pointer-events: none", grain)
        self.assertIn("position: fixed", grain)
        # Grain must sit below content without creating stacking contexts on #app-shell or the
        # landing sections; the mobile position:fixed date picker depends on that.
        self.assertIn("z-index: -1", grain)
        self.assertIn("z-index: -1", INDEX.split("#login-overlay::before {", 1)[1][:400])
        self.assertNotIn("#app-shell { position: relative; z-index: 1; }", INDEX)
        self.assertNotIn("#login-overlay > :not(.landing-header)", INDEX)
        self.assertIn("text-wrap: balance", INDEX)
        self.assertIn("text-wrap: pretty", INDEX)
        self.assertNotIn("filter: drop-shadow", INDEX)

    def test_pop_restyle_hero_stage(self):
        overlay = INDEX.split('id="login-overlay"', 1)[1].split('id="app-shell"', 1)[0]
        hero = INDEX.split('class="l-hero"', 1)[1].split('id="how"', 1)[0]
        self.assertIn('class="hero-stage"', hero)
        self.assertIn('class="mtf-text hero-text"', hero)
        self.assertIn("Sample text · 7:15 PM", hero)
        self.assertIn("New opening: California Grill", hero)
        self.assertIn('class="wand-shaft"', hero)
        self.assertNotIn('class="hero-stage"', INDEX.split('id="app-shell"', 1)[1])
        self.assertGreaterEqual(overlay.count("mtf-text"), 2)
        self.assertNotIn("Delivered", overlay)
        self.assertIn("We monitor the openings.</h1>", INDEX)
        # Ink hero: the stage is dusk ink; the Create Watch card and its legal links stay legible.
        ink_hero = INDEX.split("  .l-hero {\n    color: var(--paper);", 1)
        self.assertEqual(len(ink_hero), 2)
        self.assertIn("var(--ink);", ink_hero[1][:300])
        self.assertIn("#login-overlay .l-hero #create-watch a", INDEX)

    def test_pop_restyle_motion_is_gated(self):
        self.assertIn("prefers-reduced-motion: reduce", INDEX)
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)')", INDEX)
        self.assertIn("classList.add('mtf-motion')", INDEX)
        self.assertIn("html.mtf-motion .reveal {", INDEX)
        self.assertIn("html.mtf-motion .reveal.is-in {", INDEX)
        self.assertNotRegex(INDEX, r"\n\s*\.reveal \{")
        self.assertIn("@keyframes wand-draw", INDEX)
        self.assertIn("@keyframes text-arrive", INDEX)
        self.assertIn("startViewTransition", INDEX)
        self.assertIn("function activateTab(", INDEX)
        self.assertIn("function applyTab(", INDEX)
        self.assertNotIn("animation:", INDEX.split(".wordmark-wand-accent {", 1)[1][:400])
        self.assertNotIn("#status-dot.ok   { animation", INDEX)

    def test_pop_restyle_sections(self):
        faq = INDEX.split('id="faq"', 1)[1].split('id="signin"', 1)[0]
        self.assertEqual(faq.count("<details"), 7)
        self.assertEqual(faq.count("<summary"), 7)
        self.assertIn('class="l-steps l-rail"', INDEX)
        self.assertIn('class="l-price l-price-featured reveal"', INDEX)
        self.assertIn('class="l-sms mtf-text reveal"', INDEX)
        self.assertIn("::details-content", INDEX)
        self.assertIn(".l-faq { width: min(720px, calc(100% - 48px)); margin: 0 auto; }", INDEX)


if __name__ == "__main__":
    unittest.main()
