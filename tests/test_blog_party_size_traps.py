"""Evergreen Angle 2: party-size traps blog post stays on the locked draft."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POST = (ROOT / "public/blog/disney-dining-party-size-traps.html").read_text(encoding="utf-8")
INDEX = (ROOT / "public/blog/index.html").read_text(encoding="utf-8")

TITLE = "Party-size traps at hard Disney World restaurants (why 4 shows when 5 is gone)"
DESCRIPTION = (
    "Hard ADRs don’t share one open pool. Party size changes what Disney shows. "
    "Here’s a calm recovery path — and an optional $4.99 Single Watch for the size you still need."
)
CRT = "https://magictablefinder.com/alerts/cinderellas-royal-table"
SPACE = "https://magictablefinder.com/alerts/space-220"
OHANA = "https://magictablefinder.com/alerts/ohana"
PLAN_B1 = "https://plandisney.disney.go.com/question/party-breakfast-reservation-cinderellas-royal-table-seems-592838/"
PLAN_B2 = "https://plandisney.disney.go.com/question/question-regarding-cinderellas-royal-table-larger-607486/"
PLAN_B3 = "https://plandisney.disney.go.com/question/cinderellas-royal-table-seating-plan-splitting-group-go-599260/"


class BlogPartySizeTrapsTest(unittest.TestCase):
    def test_post_title_meta_and_canonical(self):
        self.assertIn(f"<title>{TITLE} | Magic Table Finder</title>", POST)
        self.assertIn(f"<h1>{TITLE}</h1>", POST)
        self.assertIn(f'content="{DESCRIPTION}"', POST)
        self.assertIn(
            'rel="canonical" href="https://magictablefinder.com/blog/disney-dining-party-size-traps"',
            POST,
        )
        self.assertIn('content="#f5f1e9"', POST)
        self.assertIn("https://magictablefinder.com/og-1200x630.png", POST)

    def test_index_lists_only_this_post(self):
        self.assertIn('rel="canonical" href="https://magictablefinder.com/blog"', INDEX)
        self.assertIn('href="/blog/disney-dining-party-size-traps"', INDEX)
        self.assertIn(TITLE, INDEX)
        self.assertNotIn("wrong-date", INDEX)
        self.assertNotIn("cancel", INDEX.lower())
        self.assertEqual(INDEX.count("<h1>"), 1)

    def test_plan_disney_links_match_receipts(self):
        self.assertEqual(POST.count(PLAN_B1), 1)
        self.assertEqual(POST.count(PLAN_B2), 2)
        self.assertEqual(POST.count(PLAN_B3), 2)

    def test_money_urls_clustered_once(self):
        self.assertEqual(POST.count(CRT), 1)
        self.assertEqual(POST.count(SPACE), 1)
        self.assertEqual(POST.count(OHANA), 1)
        self.assertIn(">Cinderella’s Royal Table alerts</a>", POST)
        self.assertIn(">Space 220 alerts</a>", POST)
        self.assertIn(">‘Ohana alerts</a>", POST)
        self.assertNotIn("Planner", POST)
        self.assertNotIn("$14.99", POST)
        self.assertNotIn("/#pricing", POST)

    def test_kills_stay_out_of_the_public_post(self):
        lowered = POST.lower()
        self.assertNotIn("reddit.com", lowered)
        self.assertNotIn("dining package", lowered)
        self.assertNotIn("#1", POST)
        self.assertNotIn("wrong-date", lowered)
        self.assertNotIn("cancel rebuild", lowered)
        self.assertNotIn("angle 1", lowered)
        self.assertNotIn("book 3 modify to 2", lowered)
        self.assertIn("don’t assume a toddler", POST)
        self.assertIn("modify-down tip is official booking policy", POST)
        self.assertIn("We do not guarantee a table will open.", POST)
        self.assertIn("No guarantee of a walk-up or day-of save.", POST)
        self.assertNotIn("party of 5 gone, party of 4 still shows", POST)
