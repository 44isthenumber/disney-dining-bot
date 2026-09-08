"""SEO money pages: Potato Growth pack → existing Single Watch."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
NETLIFY = (ROOT / "netlify.toml").read_text(encoding="utf-8")
CSS = (PUBLIC / "money-pages.css").read_text(encoding="utf-8")
INDEX = (PUBLIC / "index.html").read_text(encoding="utf-8")

PAGES = {
    "space-220": {
        "file": "alerts/space-220.html",
        "pretty": "/alerts/space-220",
        "title": "Space 220 reservation alerts | Magic Table Finder",
        "h1": "Sold out at Space 220? Get a text when a table opens.",
        "cta_href": "/?watch=space-220",
        "meta": "Watch Space 220 (EPCOT). We text you when a matching Walt Disney World table newly opens. You book on Disney",
    },
    "ohana": {
        "file": "alerts/ohana.html",
        "pretty": "/alerts/ohana",
        "title": "‘Ohana reservation alerts | Magic Table Finder",
        "h1": "Missed ‘Ohana at 60 days? We’ll text new openings.",
        "cta_href": "/?watch=ohana",
        "meta": "Watch ‘Ohana at Disney’s Polynesian.",
    },
    "cinderellas-royal-table": {
        "file": "alerts/cinderellas-royal-table.html",
        "pretty": "/alerts/cinderellas-royal-table",
        "title": "Cinderella’s Royal Table alerts | Magic Table Finder",
        "h1": "Castle table sold out? Text alerts for new matching opens.",
        "cta_href": "/?watch=cinderella-royal-table",
        "meta": "Watch Cinderella’s Royal Table.",
    },
}

FORBIDDEN = (
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

    def test_files_exist_with_locked_titles_and_h1s(self):
        titles = []
        h1s = []
        for key, spec in PAGES.items():
            html = self.pages[key]
            self.assertTrue((PUBLIC / spec["file"]).is_file(), spec["file"])
            self.assertIn(f"<title>{spec['title']}</title>", html)
            self.assertIn(f"<h1>{spec['h1']}</h1>", html)
            self.assertIn(spec["meta"], html)
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
            self.assertIn("$4.99", html)
            self.assertIn("Single Watch", html)
            self.assertIn("$14.99", html)
            self.assertIn('href="/#pricing"', html)
            self.assertNotIn("$9", html)
            self.assertNotIn("$19", html)

    def test_catalog_slugs_match_watch_query(self):
        catalog = (ROOT / "restaurants.json").read_text(encoding="utf-8")
        self.assertIn('"slug": "space-220"', catalog)
        self.assertIn('"name": "Space 220 Restaurant"', catalog)
        self.assertIn('"slug": "ohana"', catalog)
        self.assertIn("\"name\": \"'Ohana\"", catalog)
        self.assertIn('"slug": "cinderella-royal-table"', catalog)
        self.assertIn("\"name\": \"Cinderella's Royal Table\"", catalog)

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
        space = self.pages["space-220"]
        ohana = self.pages["ohana"]
        crt = self.pages["cinderellas-royal-table"]
        self.assertIn('href="/alerts/ohana"', space)
        self.assertIn('href="/alerts/cinderellas-royal-table"', space)
        self.assertIn('href="/alerts/space-220"', ohana)
        self.assertIn('href="/alerts/cinderellas-royal-table"', ohana)
        self.assertIn('href="/alerts/space-220"', crt)
        self.assertIn('href="/alerts/ohana"', crt)

    def test_homepage_hard_to_book_block(self):
        self.assertIn("<title>Walt Disney World dining alerts | Magic Table Finder</title>", INDEX)
        block = INDEX.split('id="hard-tables"', 1)[1].split('id="proof"', 1)[0]
        self.assertIn("Hard-to-book watches", block)
        self.assertIn('href="/alerts/space-220"', block)
        self.assertIn('href="/alerts/ohana"', block)
        self.assertIn('href="/alerts/cinderellas-royal-table"', block)

    def test_no_forbidden_copy_or_pixels(self):
        html_blob = "".join(self.pages.values())
        lowered = (html_blob + CSS).lower()
        visible = re.sub(r"<style[\s\S]*?</style>", " ", html_blob, flags=re.I)
        visible = re.sub(r"<script[\s\S]*?</script>", " ", visible, flags=re.I)
        self.assertNotRegex(visible.lower(), r"(?<![0-9a-f])#1\b")
        for phrase in FORBIDDEN:
            self.assertNotIn(phrase, lowered)
        self.assertIsNone(re.search(r"gtag\s*\(", html_blob + CSS))
        self.assertNotIn("fbq(", html_blob)
        self.assertNotIn("facebook.net", lowered)
        self.assertNotIn("fbevents", lowered)


if __name__ == "__main__":
    unittest.main()
