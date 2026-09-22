"""Evergreen Angle 3: week-out recovery blog post stays on the locked draft."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POST = (ROOT / "public/blog/disney-dining-week-out-recovery.html").read_text(encoding="utf-8")
INDEX = (ROOT / "public/blog/index.html").read_text(encoding="utf-8")

TITLE = "Your hard Disney dining table is gone a week out — what to do next"
DESCRIPTION = (
    "A week out, the hard Disney table can still be empty. "
    "Cancellations can free seats close to the meal. "
    "Here’s a calm next step — and an optional $4.99 Single Watch for one restaurant."
)
SPACE = "https://magictablefinder.com/alerts/space-220"
PLAN_A1 = "https://plandisney.disney.go.com/question/grace-period-regarding-dining-reservations-time-cancel-525702/"
DFB_A2 = "https://www.disneyfoodblog.com/2026/02/21/4-hacks-that-make-booking-magic-kingdom-dining-reservations-10x-easier/"
PREP_A3 = "https://wdwprepschool.com/difficult-disney-dining-reservations/"
PARTY_TITLE = "Party-size traps at hard Disney World restaurants (why 4 shows when 5 is gone)"


class BlogWeekOutRecoveryTest(unittest.TestCase):
    def test_post_title_meta_and_canonical(self):
        self.assertIn(f"<title>{TITLE} | Magic Table Finder</title>", POST)
        self.assertIn(f"<h1>{TITLE}</h1>", POST)
        self.assertIn(f'content="{DESCRIPTION}"', POST)
        self.assertIn(
            'rel="canonical" href="https://magictablefinder.com/blog/disney-dining-week-out-recovery"',
            POST,
        )
        self.assertIn('content="#f5f1e9"', POST)
        self.assertIn("https://magictablefinder.com/og-1200x630.png", POST)
        self.assertIn('datetime="2026-09-22"', POST)

    def test_index_lists_both_posts_newest_first(self):
        self.assertIn('rel="canonical" href="https://magictablefinder.com/blog"', INDEX)
        self.assertIn('href="/blog/disney-dining-week-out-recovery"', INDEX)
        self.assertIn('href="/blog/disney-dining-party-size-traps"', INDEX)
        self.assertIn(TITLE, INDEX)
        self.assertIn(PARTY_TITLE, INDEX)
        self.assertLess(
            INDEX.index("/blog/disney-dining-week-out-recovery"),
            INDEX.index("/blog/disney-dining-party-size-traps"),
        )
        self.assertNotIn("wrong-date", INDEX)
        self.assertNotIn("cancel", INDEX.lower())
        self.assertEqual(INDEX.count("<h1>"), 1)

    def test_citation_links_match_receipts_a1_a2_a3(self):
        self.assertEqual(POST.count(PLAN_A1), 1)
        self.assertEqual(POST.count(DFB_A2), 1)
        self.assertEqual(POST.count(PREP_A3), 1)
        self.assertNotIn("magicalblueprint.com", POST)
        self.assertNotIn("reddit.com", POST.lower())

    def test_space_220_is_the_only_money_url(self):
        self.assertEqual(POST.count(SPACE), 1)
        self.assertIn(">Space 220 reservation alerts</a>", POST)
        self.assertNotIn("/alerts/cinderellas-royal-table", POST)
        self.assertNotIn("/alerts/ohana", POST)
        self.assertIn("Same shape exists for other hard tables", POST)
        self.assertIn("Cinderella’s Royal Table", POST)
        self.assertIn("‘Ohana", POST)
        self.assertNotIn("Planner", POST)
        self.assertNotIn("$14.99", POST)
        self.assertNotIn("/#pricing", POST)

    def test_kills_stay_out_of_the_public_post(self):
        lowered = POST.lower()
        self.assertNotIn("dining package", lowered)
        self.assertNotIn("#1", POST)
        self.assertNotIn("wrong-date", lowered)
        self.assertNotIn("party-size trap", lowered)
        self.assertNotIn("modify-down", lowered)
        self.assertNotIn("modify down", lowered)
        self.assertNotIn("always works", lowered)
        self.assertNotIn("walk-up always", lowered)
        self.assertIn("it is not a reliable bet for every hard table.", POST)
        self.assertIn("Single Watch for $4.99", POST)
        self.assertIn("Not affiliated.", POST)
        self.assertIn("We do not guarantee a table will open.", POST)
        self.assertIn("not a substitute for a backup plan.", POST)
