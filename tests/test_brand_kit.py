"""Phase 1 Quiet Luxury brand-kit contract.

Guards canonical jewelry-wand SVGs, favicon/OG assets, tokens, and the
kill-list (no 5-point Disney star, no CSL red, no invented mark).
"""

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
BRAND = PUBLIC / "brand"
INDEX = (PUBLIC / "index.html").read_text(encoding="utf-8")
MARK = (BRAND / "mark.svg").read_text(encoding="utf-8")
FAVICON = (BRAND / "favicon.svg").read_text(encoding="utf-8")

LOZENGE = "29.4,9.5 32.5,14.1 29.4,18.7 26.3,14.1"
SHAFT = "24.3,53.4 19.3,51.6 28.7,13.4 30.1,14.8"
FAV_LOZENGE = "29.3,8.2 33.2,14.0 29.3,19.8 25.4,14.0"
STAR_WORDMARK = "M22.4 4.8 23.7 8.6 27.5 9.9"
STAR_HERO = "M378 34 392 72 430 86"
CSL_RED = "#EF0107"


class BrandKitTest(unittest.TestCase):
    def test_canonical_mark_svg(self):
        self.assertIn('viewBox="0 0 64 64"', MARK)
        self.assertIn('fill="#aa8b54"', MARK)
        self.assertIn(f'id="shaft" points="{SHAFT}"', MARK)
        self.assertIn('id="pommel" cx="21.8" cy="52.5"', MARK)
        self.assertIn(f'id="tip" points="{LOZENGE}"', MARK)
        self.assertIn('id="dust"', MARK)
        self.assertNotIn(STAR_WORDMARK, MARK)
        self.assertNotIn("Mickey", MARK)
        self.assertNotIn(CSL_RED.lower(), MARK.lower())

    def test_canonical_favicon_svg(self):
        self.assertIn('viewBox="0 0 64 64"', FAVICON)
        self.assertIn('fill="#f5f1e9"', FAVICON)
        self.assertIn('fill="#aa8b54"', FAVICON)
        self.assertIn(f'id="tip" points="{FAV_LOZENGE}"', FAVICON)
        self.assertIn('id="pommel" cx="21.6" cy="53.0"', FAVICON)
        self.assertEqual((PUBLIC / "favicon.svg").read_bytes(), (BRAND / "favicon.svg").read_bytes())

    def test_wordmarks_use_canonical_mark(self):
        self.assertEqual(INDEX.count('src="/brand/mark.svg"'), 2)
        overlay, _, rest = INDEX.partition('id="app-shell"')
        self.assertIn('src="/brand/mark.svg"', overlay)
        self.assertIn('src="/brand/mark.svg"', rest)
        self.assertIn(LOZENGE, INDEX)
        self.assertIn(SHAFT, INDEX)
        self.assertNotIn(STAR_WORDMARK, INDEX)
        self.assertNotIn(STAR_HERO, INDEX)

    def test_hero_uses_jewelry_anatomy(self):
        hero = INDEX.split('class="hero-wand"', 1)[1].split("</svg>", 1)[0]
        self.assertIn(LOZENGE, hero)
        self.assertIn('id="pommel"', hero)
        self.assertIn('class="wand-shaft"', hero)
        self.assertNotIn(STAR_HERO, hero)
        self.assertNotIn(STAR_WORDMARK, hero)

    def test_favicon_and_og_files(self):
        sizes = {
            PUBLIC / "favicon-16.png": (16, 16),
            PUBLIC / "favicon-32.png": (32, 32),
            PUBLIC / "favicon-48.png": (48, 48),
            PUBLIC / "favicon-64.png": (64, 64),
            PUBLIC / "apple-touch-icon.png": (180, 180),
            PUBLIC / "favicon-512.png": (512, 512),
            PUBLIC / "og-1200x630.png": (1200, 630),
        }
        for path, expected in sizes.items():
            self.assertTrue(path.is_file(), path.name)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"), path.name)
            self.assertEqual(struct.unpack(">II", data[16:24]), expected, path.name)
        self.assertTrue((PUBLIC / "favicon.ico").is_file())

    def test_html_meta_and_links(self):
        self.assertIn('href="/brand/favicon.svg"', INDEX)
        for href in (
            "/favicon-16.png",
            "/favicon-32.png",
            "/favicon-48.png",
            "/favicon-64.png",
            "/favicon-512.png",
            "/apple-touch-icon.png",
            "/favicon.ico",
        ):
            self.assertIn(f'href="{href}"', INDEX)
        self.assertIn('content="https://magictablefinder.com/og-1200x630.png"', INDEX)
        self.assertIn('property="og:image"', INDEX)
        self.assertIn('name="twitter:image"', INDEX)
        self.assertIn('name="twitter:card" content="summary_large_image"', INDEX)
        self.assertIn('<link rel="canonical" href="https://magictablefinder.com/" />', INDEX)
        self.assertIn('content="#f5f1e9"', INDEX)

    def test_legal_pages_have_favicon_and_og(self):
        for name in ("privacy.html", "terms.html", "sms-consent.html"):
            text = (PUBLIC / name).read_text(encoding="utf-8")
            self.assertIn('href="/brand/favicon.svg"', text)
            self.assertIn("og-1200x630.png", text)
            self.assertIn("--mtf-cream: #f5f1e9", text)
            self.assertNotIn("#f7f8fc", text)
            self.assertNotIn(CSL_RED.lower(), text.lower())

    def test_kill_list(self):
        lowered = INDEX.lower()
        self.assertNotIn(CSL_RED.lower(), lowered)
        self.assertNotIn("#b0894a", lowered)
        self.assertNotIn("fraunces", lowered)
        self.assertNotIn("🏰", INDEX)
        # Character branding stay out of chrome. Restaurant name / slug Chef Mickey’s is allowed.
        chrome = re.sub(r"chef[- ]mickey['\u2019]?s?", "", lowered)
        self.assertNotIn("mickey", chrome)
        self.assertNotIn(STAR_WORDMARK, INDEX)
        self.assertNotIn(STAR_HERO, INDEX)

    def test_gold_is_not_cta_flood(self):
        self.assertIn("#create-btn {\n    padding: 11px 24px; background: var(--ink);", INDEX)
        self.assertIn(".l-btn-primary { background: var(--ink);", INDEX)
        create = INDEX.split("#create-btn {", 1)[1].split("}", 1)[0]
        self.assertNotIn("var(--gold)", create)
        self.assertNotIn("var(--mtf-gold)", create)


if __name__ == "__main__":
    unittest.main()
