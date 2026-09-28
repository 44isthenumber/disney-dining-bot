"""Evergreen Angle 6: modify / grow party size blog post stays on the locked draft."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POST = (ROOT / "public/blog/disney-dining-modify-party-size.html").read_text(encoding="utf-8")
INDEX = (ROOT / "public/blog/index.html").read_text(encoding="utf-8")
PARTY = (ROOT / "public/blog/disney-dining-party-size-traps.html").read_text(encoding="utf-8")
WEEK = (ROOT / "public/blog/disney-dining-week-out-recovery.html").read_text(encoding="utf-8")
CRT_POST = (ROOT / "public/blog/cinderellas-royal-table-wrong-date-party-of-5.html").read_text(encoding="utf-8")

TITLE = "Friend joined the trip — why you can’t just add them to a hard Disney dining reservation"
DESCRIPTION = (
    "You already hold an ADR. The party grew. Modify often needs inventory for the new size. "
    "Calm path + optional $4.99 Single Watch for the size you still need."
)
SLUG = "disney-dining-modify-party-size"
CRT = "https://magictablefinder.com/alerts/cinderellas-royal-table"
PLAN_B1 = "https://plandisney.disney.go.com/question/change-number-people-dining-reservation-made-515797/"
DFB_B3 = "https://www.disneyfoodblog.com/2021/05/22/easiest-ways-to-modify-a-disney-world-dining-reservation/"
CRT_HREF = "/blog/cinderellas-royal-table-wrong-date-party-of-5"
WEEK_HREF = "/blog/disney-dining-week-out-recovery"
PARTY_HREF = "/blog/disney-dining-party-size-traps"


class BlogModifyPartySizeTest(unittest.TestCase):
    def test_post_title_meta_and_canonical(self):
        self.assertIn(f"<title>{TITLE} | Magic Table Finder</title>", POST)
        self.assertIn(f"<h1>{TITLE}</h1>", POST)
        self.assertIn(f'content="{DESCRIPTION}"', POST)
        self.assertIn(
            f'rel="canonical" href="https://magictablefinder.com/blog/{SLUG}"',
            POST,
        )
        self.assertIn(f'property="og:url" content="https://magictablefinder.com/blog/{SLUG}"', POST)
        self.assertIn('content="#f5f1e9"', POST)
        self.assertIn("https://magictablefinder.com/og-1200x630.png", POST)
        self.assertIn('datetime="2026-09-28"', POST)
        self.assertIn('<p class="blog-kicker"><a href="/blog">Blog</a></p>', POST)

    def test_index_lists_angle_6_newest_then_existing_posts(self):
        self.assertIn('rel="canonical" href="https://magictablefinder.com/blog"', INDEX)
        self.assertIn(f'href="/blog/{SLUG}"', INDEX)
        self.assertIn(TITLE, INDEX)
        self.assertLess(INDEX.index(f"/blog/{SLUG}"), INDEX.index(CRT_HREF))
        self.assertLess(INDEX.index(CRT_HREF), INDEX.index(WEEK_HREF))
        self.assertLess(INDEX.index(WEEK_HREF), INDEX.index(PARTY_HREF))
        self.assertEqual(INDEX.count("<h1>"), 1)

    def test_primary_spine_links_once_each(self):
        self.assertEqual(POST.count(PLAN_B1), 1)
        self.assertEqual(POST.count(DFB_B3), 1)
        self.assertIn("Select an Available Time", POST)
        self.assertIn("looking for inventory at the <strong>new</strong> size", POST)
        self.assertIn("you can lose that original time", POST)

    def test_crt_money_url_once_no_triple_cta(self):
        self.assertEqual(POST.count(CRT), 1)
        self.assertIn(">Cinderella’s Royal Table alerts</a>", POST)
        self.assertNotIn("/alerts/space-220", POST)
        self.assertNotIn("/alerts/ohana", POST)
        self.assertIn("Same-shape Single Watch pages exist for other hard tables (Space 220, ‘Ohana)", POST)
        self.assertNotIn("Planner", POST)
        self.assertNotIn("$14.99", POST)
        self.assertNotIn("/#pricing", POST)
        self.assertNotIn("/#signin\">", POST.split("<main", 1)[1])
        self.assertIn("Single Watch", POST)
        self.assertIn("$4.99", POST)

    def test_hard_non_claims_stay_out_of_the_public_post(self):
        lowered = POST.lower()
        self.assertNotIn("reddit", lowered)
        self.assertNotIn("1sr2417", lowered)
        self.assertNotIn("disboards", lowered)
        self.assertNotIn("recently changed", lowered)
        self.assertNotIn("changed the app", lowered)
        self.assertNotIn("closed the loophole", lowered)
        self.assertNotIn("closed a loophole", lowered)
        self.assertNotIn("system change", lowered)
        self.assertNotIn("dining package", lowered)
        self.assertNotIn("#1", POST)
        self.assertNotIn("angle 1", lowered)
        self.assertNotIn("angle 2", lowered)
        self.assertNotIn("angle 3", lowered)
        self.assertNotIn("wrong-date", lowered)
        self.assertNotIn("party-size trap", lowered)
        self.assertNotIn("week out", lowered)
        self.assertNotIn("guaranteed", lowered)
        self.assertNotIn("will seat", lowered)
        # Book-large-then-shrink and loophole talk appear only as explicit non-claims.
        self.assertIn("do not publish “book a larger party then shrink later,”", POST)
        self.assertIn("any tip framed as Disney closing a loophole, as official booking rules", POST)
        self.assertIn("asking at the host stand is a request only", POST)
        self.assertIn("Do not assume a smaller ADR covers a larger walk-in party.", POST)
        self.assertIn("No guarantee of a walk-up or day-of save.", POST)
        self.assertIn("We do not guarantee a table will open.", POST)
        self.assertIn("Not affiliated with Disney.", POST)
        self.assertIn("not a substitute for a backup plan.", POST)

    def test_other_posts_are_untouched_bodies(self):
        self.assertIn("Party-size traps at hard Disney World restaurants", PARTY)
        self.assertIn("Your hard Disney dining table is gone a week out", WEEK)
        self.assertIn("Wrong-date cancel at Cinderella’s Royal Table", CRT_POST)
        for other in (PARTY, WEEK, CRT_POST):
            self.assertNotIn(SLUG, other)
            self.assertNotIn(PLAN_B1, other)
