"""SEO money pages: real HTML, pretty routes, Single Watch CTAs, Quiet Luxury."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
NETLIFY = (ROOT / "netlify.toml").read_text(encoding="utf-8")
CSS = (PUBLIC / "money-pages.css").read_text(encoding="utf-8")

PAGES = {
    "disney-world-dining-alerts": {
        "file": "disney-world-dining-alerts.html",
        "pretty": "/disney-world-dining-alerts",
        "title": "Disney World dining reservation alerts | Magic Table Finder",
        "h1": "Disney World dining reservation alerts",
        "cta_href": "/",
        "cta_copy": "Start a watch · $4.99",
    },
    "be-our-guest-dining-alerts": {
        "file": "be-our-guest-dining-alerts.html",
        "pretty": "/be-our-guest-dining-alerts",
        "title": "Be Our Guest dining alerts | Magic Table Finder",
        "h1": "Be Our Guest dining alerts",
        "cta_href": "/?watch=be-our-guest-restaurant",
        "cta_copy": "Watch Be Our Guest · $4.99",
    },
    "california-grill-dining-alerts": {
        "file": "california-grill-dining-alerts.html",
        "pretty": "/california-grill-dining-alerts",
        "title": "California Grill dining alerts | Magic Table Finder",
        "h1": "California Grill dining alerts",
        "cta_href": "/?watch=california-grill",
        "cta_copy": "Watch California Grill · $4.99",
    },
}

FORBIDDEN = (
    "#1",
    "number one",
    "best disney dining alert",
    "mousewatcher",
    "mousedining",
    "mouse watcher",
    "fbevents",
    "facebook.net",
    "gtag(",
    "every 10 min",
    "every 10 minutes",
    "#ef0107",
    "fraunces",
)


class MoneyPagesTest(unittest.TestCase):
    def setUp(self):
        self.pages = {
            key: (PUBLIC / spec["file"]).read_text(encoding="utf-8")
            for key, spec in PAGES.items()
        }

    def test_files_exist_with_unique_h1_and_title(self):
        titles = []
        h1s = []
        for key, spec in PAGES.items():
            html = self.pages[key]
            self.assertTrue((PUBLIC / spec["file"]).is_file(), spec["file"])
            self.assertIn(f"<title>{spec['title']}</title>", html)
            self.assertIn(f"<h1>{spec['h1']}</h1>", html)
            titles.append(spec["title"])
            h1s.append(spec["h1"])
        self.assertEqual(len(set(titles)), 3)
        self.assertEqual(len(set(h1s)), 3)

    def test_pretty_rewrites_and_no_splat(self):
        self.assertNotRegex(NETLIFY, r'from = "/\*"\s+to = "/index.html"')
        for spec in PAGES.values():
            self.assertIn(f'from = "{spec["pretty"]}"', NETLIFY)
            self.assertIn(f'to = "/{spec["file"]}"', NETLIFY)
            block = NETLIFY.split(f'from = "{spec["pretty"]}"', 1)[1][:220]
            self.assertIn("status = 200", block)

    def test_seo_head_tags(self):
        for key, spec in PAGES.items():
            html = self.pages[key]
            canonical = f'https://magictablefinder.com{spec["pretty"]}'
            self.assertIn(f'<link rel="canonical" href="{canonical}">', html)
            self.assertRegex(html, r'<meta name="description" content="[^"]{40,}">')
            self.assertIn('href="/brand/favicon.svg"', html)
            self.assertIn("og-1200x630.png", html)
            self.assertIn('name="twitter:card" content="summary_large_image"', html)
            self.assertIn('name="theme-color" content="#f5f1e9"', html)
            self.assertIn(f'property="og:url" content="{canonical}"', html)

    def test_primary_cta_is_existing_single_watch(self):
        for key, spec in PAGES.items():
            html = self.pages[key]
            self.assertIn(f'class="mp-btn mp-btn-primary" href="{spec["cta_href"]}"', html)
            self.assertIn(spec["cta_copy"], html)
            self.assertIn("Single Watch", html)
            self.assertIn("$4.99", html)
            self.assertIn("$14.99", html)
            self.assertNotIn("$9", html)
            self.assertNotIn("$19", html)

    def test_ink_cta_not_gold_flood(self):
        self.assertIn(".mp-btn-primary {", CSS)
        primary = CSS.split(".mp-btn-primary {", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--mtf-ink)", primary)
        self.assertNotIn("var(--mtf-gold)", primary)
        self.assertNotIn("#aa8b54", primary)

    def test_quiet_luxury_tokens(self):
        self.assertIn("--mtf-cream: #f5f1e9", CSS)
        self.assertIn("--mtf-gold: #aa8b54", CSS)
        self.assertIn("--mtf-ink: #000000", CSS)
        self.assertIn("Playfair Display", CSS)
        self.assertIn("Inter", CSS)
        for html in self.pages.values():
            self.assertIn('href="/money-pages.css"', html)
            self.assertIn("Playfair+Display", html)
            self.assertIn("family=Inter", html)

    def test_legal_voice_and_footer_hrefs(self):
        for html in self.pages.values():
            self.assertIn("not affiliated", html.lower())
            self.assertIn("We do not guarantee a table will open.", html)
            self.assertIn('href="/privacy.html"', html)
            self.assertIn('href="/terms.html"', html)
            self.assertIn('href="/sms-consent.html"', html)
            self.assertIn('href="/"', html)

    def test_sibling_cross_links(self):
        umbrella = self.pages["disney-world-dining-alerts"]
        bog = self.pages["be-our-guest-dining-alerts"]
        cg = self.pages["california-grill-dining-alerts"]
        self.assertIn('href="/be-our-guest-dining-alerts"', umbrella)
        self.assertIn('href="/california-grill-dining-alerts"', umbrella)
        self.assertIn("Space 220 Restaurant", umbrella)
        self.assertIn('href="/disney-world-dining-alerts"', bog)
        self.assertIn('href="/california-grill-dining-alerts"', bog)
        self.assertIn('href="/disney-world-dining-alerts"', cg)
        self.assertIn('href="/be-our-guest-dining-alerts"', cg)

    def test_no_forbidden_copy_or_pixels(self):
        html_blob = "".join(self.pages.values())
        lowered = (html_blob + CSS).lower()
        visible = re.sub(r"<style[\s\S]*?</style>", " ", html_blob, flags=re.I)
        visible = re.sub(r"<script[\s\S]*?</script>", " ", visible, flags=re.I)
        visible_l = visible.lower()
        self.assertNotRegex(visible_l, r"(?<![0-9a-f])#1\b")
        for phrase in FORBIDDEN:
            if phrase == "#1":
                continue
            self.assertNotIn(phrase, lowered)
        self.assertIsNone(re.search(r"gtag\s*\(", html_blob + CSS))
        self.assertNotIn("fbq(", html_blob)
        self.assertNotIn("facebook.net", lowered)
        self.assertNotIn("fbevents", lowered)


if __name__ == "__main__":
    unittest.main()
