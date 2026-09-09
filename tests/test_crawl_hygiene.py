"""Crawl hygiene: robots, sitemap, canonical, favicons, and no homepage soft-404."""

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
NOT_FOUND = (PUBLIC / "404.html").read_text(encoding="utf-8")


class CrawlHygieneTest(unittest.TestCase):
    def test_robots_is_plain_text_not_html(self):
        self.assertTrue(ROBOTS.lstrip().startswith("User-agent:"))
        self.assertIn("Sitemap: https://magictablefinder.com/sitemap.xml", ROBOTS)
        self.assertNotIn("Disallow: /sms-consent", ROBOTS)
        self.assertNotIn("<!DOCTYPE html", ROBOTS)
        self.assertNotIn("<html", ROBOTS)

    def test_sitemap_uses_pretty_public_urls(self):
        root = ET.fromstring(SITEMAP)
        self.assertTrue(root.tag.endswith("urlset"))
        locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
        self.assertEqual(
            locs,
            [
                "https://magictablefinder.com/",
                "https://magictablefinder.com/privacy",
                "https://magictablefinder.com/terms",
                "https://magictablefinder.com/sms-consent",
                "https://magictablefinder.com/alerts/space-220",
                "https://magictablefinder.com/alerts/ohana",
                "https://magictablefinder.com/alerts/cinderellas-royal-table",
                "https://magictablefinder.com/alerts/california-grill",
                "https://magictablefinder.com/alerts/be-our-guest",
                "https://magictablefinder.com/alerts/topolinos-terrace",
                "https://magictablefinder.com/alerts/chef-mickeys",
                "https://magictablefinder.com/alerts/sci-fi-dine-in",
                "https://magictablefinder.com/alerts/yachtsman-steakhouse",
            ],
        )
        self.assertNotIn("text-consent", SITEMAP)
        self.assertNotIn(".html", SITEMAP)
        self.assertNotIn("<!DOCTYPE html", SITEMAP)

    def test_sitemap_index_is_xml_not_html(self):
        root = ET.fromstring(SITEMAP_INDEX)
        self.assertTrue(root.tag.endswith("sitemapindex"))
        locs = [el.text for el in root.iter() if el.tag.endswith("loc")]
        self.assertEqual(locs, ["https://magictablefinder.com/sitemap.xml"])
        self.assertNotIn("<!DOCTYPE html", SITEMAP_INDEX)

    def test_netlify_has_no_homepage_soft_404_splat(self):
        self.assertNotRegex(NETLIFY, r'from = "/\*"\s+to = "/index.html"')
        self.assertIn('from = "/privacy"', NETLIFY)
        self.assertIn('from = "/terms"', NETLIFY)
        self.assertIn('from = "/sms-consent"', NETLIFY)
        self.assertIn('from = "/alerts/space-220"', NETLIFY)
        self.assertIn('from = "/alerts/ohana"', NETLIFY)
        self.assertIn('from = "/alerts/cinderellas-royal-table"', NETLIFY)
        self.assertIn('from = "/alerts/california-grill"', NETLIFY)
        self.assertIn('from = "/alerts/be-our-guest"', NETLIFY)
        self.assertIn('from = "/alerts/topolinos-terrace"', NETLIFY)
        self.assertIn('from = "/alerts/chef-mickeys"', NETLIFY)
        self.assertIn('from = "/alerts/sci-fi-dine-in"', NETLIFY)
        self.assertIn('from = "/alerts/yachtsman-steakhouse"', NETLIFY)
        self.assertIn('to = "/privacy.html"', NETLIFY)
        self.assertIn('to = "/sms-consent.html"', NETLIFY)
        self.assertIn('to = "/alerts/space-220.html"', NETLIFY)
        self.assertIn('to = "/alerts/ohana.html"', NETLIFY)
        self.assertIn('to = "/alerts/cinderellas-royal-table.html"', NETLIFY)
        self.assertIn('to = "/alerts/california-grill.html"', NETLIFY)
        self.assertIn('to = "/alerts/be-our-guest.html"', NETLIFY)
        self.assertIn('to = "/alerts/topolinos-terrace.html"', NETLIFY)
        self.assertIn('to = "/alerts/chef-mickeys.html"', NETLIFY)
        self.assertIn('to = "/alerts/sci-fi-dine-in.html"', NETLIFY)
        self.assertIn('to = "/alerts/yachtsman-steakhouse.html"', NETLIFY)
        self.assertIn('from = "/text-consent"', NETLIFY)
        self.assertIn('Content-Type = "text/plain; charset=utf-8"', NETLIFY)
        self.assertIn('Content-Type = "application/xml; charset=utf-8"', NETLIFY)
        self.assertTrue((PUBLIC / "404.html").is_file())
        self.assertIn('name="robots" content="noindex"', NOT_FOUND)
        self.assertIn("This page isn’t here.", NOT_FOUND)

    def test_homepage_canonical_share_meta_and_favicon(self):
        self.assertIn('<link rel="canonical" href="https://magictablefinder.com/" />', INDEX)
        self.assertIn('rel="icon" href="/brand/favicon.svg"', INDEX)
        self.assertIn('rel="apple-touch-icon" href="/apple-touch-icon.png"', INDEX)
        self.assertIn('property="og:image"', INDEX)
        self.assertIn('content="https://magictablefinder.com/og-1200x630.png"', INDEX)
        self.assertIn('name="twitter:card" content="summary_large_image"', INDEX)
        self.assertIn('name="twitter:image"', INDEX)
