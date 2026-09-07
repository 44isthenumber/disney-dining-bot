"""Crawl hygiene: robots, sitemap, and homepage canonical must not be the SPA shell."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
INDEX = (PUBLIC / "index.html").read_text(encoding="utf-8")
NETLIFY = (ROOT / "netlify.toml").read_text(encoding="utf-8")
ROBOTS = (PUBLIC / "robots.txt").read_text(encoding="utf-8")
SITEMAP = (PUBLIC / "sitemap.xml").read_text(encoding="utf-8")
SITEMAP_INDEX = (PUBLIC / "sitemap_index.xml").read_text(encoding="utf-8")


class CrawlHygieneTest(unittest.TestCase):
    def test_robots_is_plain_text_not_html(self):
        self.assertTrue(ROBOTS.lstrip().startswith("User-agent:"))
        self.assertIn("Sitemap: https://magictablefinder.com/sitemap.xml", ROBOTS)
        self.assertNotIn("<!DOCTYPE html", ROBOTS)
        self.assertNotIn("<html", ROBOTS)

    def test_sitemap_is_xml_not_html(self):
        root = ET.fromstring(SITEMAP)
        self.assertTrue(root.tag.endswith("urlset"))
        locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
        self.assertIn("https://magictablefinder.com/", locs)
        self.assertIn("https://magictablefinder.com/privacy.html", locs)
        self.assertIn("https://magictablefinder.com/terms.html", locs)
        self.assertIn("https://magictablefinder.com/sms-consent.html", locs)
        self.assertNotIn("<!DOCTYPE html", SITEMAP)

    def test_sitemap_index_is_xml_not_html(self):
        root = ET.fromstring(SITEMAP_INDEX)
        self.assertTrue(root.tag.endswith("sitemapindex"))
        locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
        self.assertEqual(locs, ["https://magictablefinder.com/sitemap.xml"])
        self.assertNotIn("<!DOCTYPE html", SITEMAP_INDEX)

    def test_netlify_pins_crawler_mime_and_does_not_force_spa_over_static(self):
        self.assertIn('for = "/robots.txt"', NETLIFY)
        self.assertIn('Content-Type = "text/plain; charset=utf-8"', NETLIFY)
        self.assertIn('for = "/sitemap.xml"', NETLIFY)
        self.assertIn('for = "/sitemap_index.xml"', NETLIFY)
        self.assertIn('Content-Type = "application/xml; charset=utf-8"', NETLIFY)
        splat = re.search(
            r'\[\[redirects\]\]\s+from = "/\*"\s+to = "/index.html"\s+status = 200(?:\s+force = true)?',
            NETLIFY,
        )
        self.assertIsNotNone(splat)
        self.assertNotIn("force = true", splat.group(0))

    def test_homepage_canonical_and_share_meta(self):
        self.assertIn('<link rel="canonical" href="https://magictablefinder.com/" />', INDEX)
        self.assertIn('property="og:image"', INDEX)
        self.assertIn('content="https://magictablefinder.com/og-1200x630.png"', INDEX)
        self.assertIn('name="twitter:card" content="summary_large_image"', INDEX)
        self.assertIn('name="twitter:image"', INDEX)


if __name__ == "__main__":
    unittest.main()
