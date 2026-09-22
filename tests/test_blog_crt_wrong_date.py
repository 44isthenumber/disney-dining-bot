"""Evergreen Angle 1: CRT wrong-date cancel blog post stays on the locked draft."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POST = (ROOT / "public/blog/cinderellas-royal-table-wrong-date-party-of-5.html").read_text(encoding="utf-8")
INDEX = (ROOT / "public/blog/index.html").read_text(encoding="utf-8")
PARTY = (ROOT / "public/blog/disney-dining-party-size-traps.html").read_text(encoding="utf-8")
WEEK = (ROOT / "public/blog/disney-dining-week-out-recovery.html").read_text(encoding="utf-8")

TITLE = (
    "Wrong-date cancel at Cinderella’s Royal Table: "
    "when party-of-5 is gone and you’re a week out"
)
DESCRIPTION = (
    "Cancelled the wrong date at Cinderella’s Royal Table and now party-of-5 is gone "
    "a week before your trip? Here’s a calm recovery path — and an optional $4.99 "
    "Single Watch if you still need that table."
)
SLUG = "cinderellas-royal-table-wrong-date-party-of-5"
CRT = "https://magictablefinder.com/alerts/cinderellas-royal-table"
PLAN_B1 = "https://plandisney.disney.go.com/question/party-breakfast-reservation-cinderellas-royal-table-seems-592838/"
PLAN_B3 = "https://plandisney.disney.go.com/question/question-regarding-cinderellas-royal-table-larger-607486/"
PLAN_B2 = "https://plandisney.disney.go.com/question/cinderellas-royal-table-seating-plan-splitting-group-go-599260/"
WEEK_HREF = "/blog/disney-dining-week-out-recovery"
PARTY_HREF = "/blog/disney-dining-party-size-traps"


class BlogCrtWrongDateTest(unittest.TestCase):
    def test_post_title_meta_and_canonical(self):
        self.assertIn(f"<title>{TITLE} | Magic Table Finder</title>", POST)
        self.assertIn(f"<h1>{TITLE}</h1>", POST)
        self.assertIn(f'content="{DESCRIPTION}"', POST)
        self.assertIn(
            f'rel="canonical" href="https://magictablefinder.com/blog/{SLUG}"',
            POST,
        )
        self.assertIn('content="#f5f1e9"', POST)
        self.assertIn("https://magictablefinder.com/og-1200x630.png", POST)
        self.assertIn('datetime="2026-09-22"', POST)

    def test_index_lists_angle_1_newest_then_existing_posts(self):
        self.assertIn('rel="canonical" href="https://magictablefinder.com/blog"', INDEX)
        self.assertIn(f'href="/blog/{SLUG}"', INDEX)
        self.assertIn(WEEK_HREF, INDEX)
        self.assertIn(PARTY_HREF, INDEX)
        self.assertIn(TITLE, INDEX)
        self.assertLess(INDEX.index(f"/blog/{SLUG}"), INDEX.index(WEEK_HREF))
        self.assertLess(INDEX.index(WEEK_HREF), INDEX.index(PARTY_HREF))
        self.assertEqual(INDEX.count("<h1>"), 1)

    def test_plan_disney_links_once_each(self):
        self.assertEqual(POST.count(PLAN_B1), 1)
        self.assertEqual(POST.count(PLAN_B3), 1)
        self.assertEqual(POST.count(PLAN_B2), 1)

    def test_crt_money_url_once(self):
        self.assertEqual(POST.count(CRT), 1)
        self.assertIn(">Cinderella’s Royal Table alerts</a>", POST)
        self.assertNotIn("/alerts/space-220", POST)
        self.assertNotIn("/alerts/ohana", POST)
        self.assertNotIn("Planner", POST)
        self.assertNotIn("$14.99", POST)
        self.assertNotIn("/#pricing", POST)

    def test_kills_stay_out_of_the_public_post(self):
        lowered = POST.lower()
        self.assertNotIn("reddit.com", lowered)
        self.assertNotIn("1wk4pnw", lowered)
        self.assertNotIn("dining package", lowered)
        self.assertNotIn("#1", POST)
        self.assertNotIn("angle 2", lowered)
        self.assertNotIn("angle 3", lowered)
        self.assertIn("don’t assume a toddler", POST)
        self.assertIn("party-of-4 hold magically covers five", POST)
        self.assertIn("We do not guarantee a table will open.", POST)
        self.assertIn("Not affiliated with Disney.", POST)
        self.assertIn("Single Watch", POST)
        self.assertIn("$4.99", POST)

    def test_other_posts_are_untouched_bodies(self):
        self.assertIn("Party-size traps at hard Disney World restaurants", PARTY)
        self.assertIn("Your hard Disney dining table is gone a week out", WEEK)
        self.assertNotIn(SLUG, PARTY)
        self.assertNotIn(SLUG, WEEK)
        self.assertNotIn("wrong-date", PARTY.lower())
        self.assertNotIn("wrong-date", WEEK.lower())
