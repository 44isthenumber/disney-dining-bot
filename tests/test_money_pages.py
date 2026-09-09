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
        "title": "'Ohana reservation alerts | Magic Table Finder",
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
    "california-grill": {
        "file": "alerts/california-grill.html",
        "pretty": "/alerts/california-grill",
        "title": "California Grill reservation alerts | Magic Table Finder",
        "h1": "California Grill booked up? We’ll text matching opens.",
        "cta_href": "/?watch=california-grill",
        "meta": "Watch California Grill at Disney’s Contemporary.",
        "catalog_slug": "california-grill",
        "catalog_name": "California Grill",
    },
    "be-our-guest": {
        "file": "alerts/be-our-guest.html",
        "pretty": "/alerts/be-our-guest",
        "title": "Be Our Guest reservation alerts | Magic Table Finder",
        "h1": "Be Our Guest gone at 60 days? Text alerts for new tables.",
        "cta_href": "/?watch=be-our-guest-restaurant",
        "meta": "Watch Be Our Guest Restaurant in Magic Kingdom.",
        "catalog_slug": "be-our-guest-restaurant",
        "catalog_name": "Be Our Guest Restaurant",
    },
    "topolinos-terrace": {
        "file": "alerts/topolinos-terrace.html",
        "pretty": "/alerts/topolinos-terrace",
        "title": "Topolino’s Terrace reservation alerts | Magic Table Finder",
        "h1": "Topolino’s Terrace full? We’ll text when a table opens.",
        "cta_href": "/?watch=topolinos-terrace",
        "meta": "Watch Topolino’s Terrace at Disney’s Riviera.",
        "catalog_slug": "topolinos-terrace",
        "catalog_name": "Topolino's Terrace",
    },
    "chef-mickeys": {
        "file": "alerts/chef-mickeys.html",
        "pretty": "/alerts/chef-mickeys",
        "title": "Chef Mickey’s reservation alerts | Magic Table Finder",
        "h1": "Chef Mickey’s sold out? Get a text when a table opens.",
        "cta_href": "/?watch=chef-mickeys",
        "meta": "Watch Chef Mickey’s at Disney’s Contemporary. We text when a matching table newly opens. You book on Disney’s site.",
        "catalog_slug": "chef-mickeys",
        "catalog_name": "Chef Mickey's",
    },
    "sci-fi-dine-in": {
        "file": "alerts/sci-fi-dine-in.html",
        "pretty": "/alerts/sci-fi-dine-in",
        "title": "Sci-Fi Dine-In reservation alerts | Magic Table Finder",
        "h1": "Sci-Fi Dine-In booked up? We’ll text matching opens.",
        "cta_href": "/?watch=sci-fi-dine-in-theater",
        "meta": "Watch Sci-Fi Dine-In Theater Restaurant at Hollywood Studios. We text when a matching table newly opens. You book on Disney’s site.",
        "catalog_slug": "sci-fi-dine-in-theater",
        "catalog_name": "Sci-Fi Dine-In Theater Restaurant",
    },
    "yachtsman-steakhouse": {
        "file": "alerts/yachtsman-steakhouse.html",
        "pretty": "/alerts/yachtsman-steakhouse",
        "title": "Yachtsman Steakhouse reservation alerts | Magic Table Finder",
        "h1": "Yachtsman Steakhouse full? We’ll text when a table opens.",
        "cta_href": "/?watch=yachtsman-steakhouse",
        "meta": "Watch Yachtsman Steakhouse at Disney’s Yacht Club. We text when a matching table newly opens. You book on Disney’s site.",
        "catalog_slug": "yachtsman-steakhouse",
        "catalog_name": "Yachtsman Steakhouse",
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
        self.assertEqual(len(set(titles)), len(PAGES))
        self.assertEqual(len(set(h1s)), len(PAGES))

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
            self.assertIn(f'property="og:title" content="{spec["title"]}"', html)
            self.assertIn(f'property="og:description" content="{spec["meta"]}', html)
            self.assertIn(f'name="twitter:title" content="{spec["title"]}"', html)
            self.assertIn(f'name="twitter:description" content="{spec["meta"]}', html)

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
        self.assertIn('"slug": "california-grill"', catalog)
        self.assertIn('"name": "California Grill"', catalog)
        self.assertIn('"slug": "be-our-guest-restaurant"', catalog)
        self.assertIn('"name": "Be Our Guest Restaurant"', catalog)
        self.assertIn('"slug": "topolinos-terrace"', catalog)
        self.assertIn("\"name\": \"Topolino's Terrace", catalog)
        self.assertIn('"slug": "chef-mickeys"', catalog)
        self.assertIn("\"name\": \"Chef Mickey's\"", catalog)
        self.assertIn('"slug": "sci-fi-dine-in-theater"', catalog)
        self.assertIn('"name": "Sci-Fi Dine-In Theater Restaurant"', catalog)
        self.assertIn('"slug": "yachtsman-steakhouse"', catalog)
        self.assertIn('"name": "Yachtsman Steakhouse"', catalog)

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
        california = self.pages["california-grill"]
        be_our_guest = self.pages["be-our-guest"]
        topolino = self.pages["topolinos-terrace"]
        chef = self.pages["chef-mickeys"]
        sci_fi = self.pages["sci-fi-dine-in"]
        yachtsman = self.pages["yachtsman-steakhouse"]
        for html in (california, be_our_guest, topolino, chef, sci_fi, yachtsman):
            existing = sum(
                1
                for href in (
                    "/alerts/space-220",
                    "/alerts/ohana",
                    "/alerts/cinderellas-royal-table",
                )
                if f'href="{href}"' in html
            )
            self.assertGreaterEqual(existing, 2)

    def test_homepage_hard_to_book_block(self):
        self.assertIn("<title>Walt Disney World Dining Alerts | Magic Table Finder</title>", INDEX)
        block = INDEX.split('id="hard-tables"', 1)[1].split('id="proof"', 1)[0]
        self.assertIn("Hard-to-book watches", block)
        self.assertIn("Nine restaurants.", block)
        self.assertIn('href="/alerts/space-220"', block)
        self.assertIn('href="/alerts/ohana"', block)
        self.assertIn('href="/alerts/cinderellas-royal-table"', block)
        self.assertIn('href="/alerts/california-grill"', block)
        self.assertIn('href="/alerts/be-our-guest"', block)
        self.assertIn('href="/alerts/topolinos-terrace"', block)
        self.assertIn('href="/alerts/chef-mickeys"', block)
        self.assertIn('href="/alerts/sci-fi-dine-in"', block)
        self.assertIn('href="/alerts/yachtsman-steakhouse"', block)

    def test_cta_watch_slugs_resolve_in_catalog(self):
        import json

        catalog = json.loads((ROOT / "restaurants.json").read_text(encoding="utf-8"))
        by_slug = {row["slug"]: row for row in catalog["restaurants"]}
        later = (
            "california-grill",
            "be-our-guest",
            "topolinos-terrace",
            "chef-mickeys",
            "sci-fi-dine-in",
            "yachtsman-steakhouse",
        )
        for key in later:
            spec = PAGES[key]
            slug = spec["cta_href"].split("watch=", 1)[1]
            self.assertEqual(slug, spec["catalog_slug"])
            self.assertIn(slug, by_slug)
            self.assertIn(spec["catalog_name"], by_slug[slug]["name"])
        self.assertEqual(PAGES["be-our-guest"]["pretty"], "/alerts/be-our-guest")
        self.assertEqual(PAGES["be-our-guest"]["cta_href"], "/?watch=be-our-guest-restaurant")
        self.assertNotEqual(
            PAGES["be-our-guest"]["catalog_slug"],
            PAGES["be-our-guest"]["pretty"].rsplit("/", 1)[-1],
        )
        self.assertEqual(PAGES["sci-fi-dine-in"]["pretty"], "/alerts/sci-fi-dine-in")
        self.assertEqual(PAGES["sci-fi-dine-in"]["cta_href"], "/?watch=sci-fi-dine-in-theater")
        self.assertNotEqual(
            PAGES["sci-fi-dine-in"]["catalog_slug"],
            PAGES["sci-fi-dine-in"]["pretty"].rsplit("/", 1)[-1],
        )

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
