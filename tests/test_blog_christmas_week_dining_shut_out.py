"""Christmas-week dining shut-out blog post stays on the locked draft."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POST = (ROOT / "public/blog/disney-christmas-week-dining-shut-out.html").read_text(encoding="utf-8")
INDEX = (ROOT / "public/blog/index.html").read_text(encoding="utf-8")
OFFSITE = (ROOT / "public/blog/disney-dining-off-site-60-day-head-start.html").read_text(encoding="utf-8")
MODIFY = (ROOT / "public/blog/disney-dining-modify-party-size.html").read_text(encoding="utf-8")

TITLE = "Shut out of Christmas-week Disney dining at 60 days? What can still reopen"
DESCRIPTION = (
    "Christmas Eve or Day Disney dining gone at 60 days? Why holiday tables can reopen, "
    "the package traps to know, and a $4.99 Single Watch for your one table."
)
SLUG = "disney-christmas-week-dining-shut-out"
CALIFORNIA_GRILL = "https://magictablefinder.com/alerts/california-grill"
OFFSITE_HREF = "/blog/disney-dining-off-site-60-day-head-start"
WEEK_HREF = "/blog/disney-dining-week-out-recovery"
MODIFY_HREF = "/blog/disney-dining-modify-party-size"
OFFSITE_SLUG = "disney-dining-off-site-60-day-head-start"


class BlogChristmasWeekDiningShutOutTest(unittest.TestCase):
    def test_post_title_meta_and_canonical(self):
        self.assertIn(f"<title>{TITLE} | Magic Table Finder</title>", POST)
        self.assertIn(f"<h1>{TITLE}</h1>", POST)
        self.assertIn(f'content="{DESCRIPTION}"', POST)
        self.assertLessEqual(len(DESCRIPTION), 155)
        self.assertIn(
            f'rel="canonical" href="https://magictablefinder.com/blog/{SLUG}"',
            POST,
        )
        self.assertIn(f'property="og:url" content="https://magictablefinder.com/blog/{SLUG}"', POST)
        self.assertIn(f'property="og:title" content="{TITLE} | Magic Table Finder"', POST)
        self.assertIn(f'property="og:description" content="{DESCRIPTION}"', POST)
        self.assertIn(f'name="twitter:title" content="{TITLE} | Magic Table Finder"', POST)
        self.assertIn(f'name="twitter:description" content="{DESCRIPTION}"', POST)
        self.assertIn('content="#f5f1e9"', POST)
        self.assertIn("https://magictablefinder.com/og-1200x630.png", POST)
        self.assertIn('datetime="2026-11-04"', POST)
        self.assertIn("November 4, 2026", POST)
        self.assertIn('<p class="blog-kicker"><a href="/blog">Blog</a></p>', POST)
        self.assertIn('<article class="blog-article">', POST)

    def test_index_lists_this_post_first(self):
        self.assertIn('rel="canonical" href="https://magictablefinder.com/blog"', INDEX)
        self.assertIn(f'href="/blog/{SLUG}"', INDEX)
        self.assertIn(TITLE, INDEX)
        self.assertIn("November 4, 2026", INDEX)
        self.assertLess(INDEX.index(f"/blog/{SLUG}"), INDEX.index(f"/blog/{OFFSITE_SLUG}"))
        self.assertLess(INDEX.index(f"/blog/{OFFSITE_SLUG}"), INDEX.index(MODIFY_HREF))
        self.assertEqual(INDEX.count("<h1>"), 1)

    def test_locked_draft_sections(self):
        self.assertIn("<h3>The calendar math</h3>", POST)
        self.assertIn("<h3>Why tables can come back</h3>", POST)
        self.assertIn("<h3>The traps</h3>", POST)
        self.assertIn("<h3>What you can do yourself</h3>", POST)
        self.assertIn("<h3>If you have one table that has to happen</h3>", POST)
        self.assertEqual(POST.count("<h3>"), 5)
        self.assertIn("Christmas Eve opened on October 25 and Christmas Day on October 26", POST)
        self.assertIn("checking in December 20, 2026 could book both holiday meals on October 21", POST)
        self.assertIn("$10-per-person fee only if you cancel within 2 hours", POST)
        self.assertIn("Reservations can't be modified within 2 hours of the time.", POST)
        self.assertIn("A dining reservation is not a Candlelight seat.", POST)
        self.assertIn("Nov 27 to Dec 30, 2026", POST)
        self.assertIn("plus a park reservation if your ticket type requires one", POST)
        self.assertNotIn("<h2>Sources", POST)
        self.assertNotIn("FACT_GATE", POST)
        self.assertNotIn("disneyfoodblog.com", POST)
        self.assertNotIn("disneytouristblog.com", POST)
        self.assertNotIn("disneyworld.disney.go.com/faq", POST)

    def test_california_grill_is_the_only_money_url(self):
        self.assertEqual(POST.count(CALIFORNIA_GRILL), 1)
        self.assertIn(">Watch California Grill — Single Watch, $4.99</a>", POST)
        self.assertNotIn("/alerts/cinderellas-royal-table", POST)
        self.assertNotIn("/alerts/space-220", POST)
        self.assertNotIn("Planner", POST)
        self.assertNotIn("$14.99", POST)
        self.assertNotIn("/#pricing", POST)
        self.assertIn("<strong>$4.99 Single Watch</strong> covers", POST)
        self.assertIn("We watch; you book.", POST)
        self.assertIn("No table is guaranteed.", POST)
        self.assertIn("not affiliated with Disney", POST)

    def test_internal_links(self):
        self.assertEqual(POST.count(OFFSITE_HREF), 1)
        self.assertIn(">off-site 60-day guide</a>", POST)
        self.assertEqual(POST.count(WEEK_HREF), 1)
        self.assertIn(">week-out recovery guide</a>", POST)

    def test_hard_non_claims_stay_out_of_the_public_post(self):
        lowered = POST.lower()
        article = POST.split("<article", 1)[1].split("</article>", 1)[0].lower()
        self.assertNotIn("the moment", lowered)
        self.assertNotIn("the second", lowered)
        self.assertNotIn("instantly", lowered)
        self.assertNotIn("in minutes", lowered)
        self.assertIn("no table is guaranteed.", article)
        self.assertEqual(article.count("guaranteed"), 1)
        self.assertNotIn("reddit", lowered)
        self.assertNotIn("disboards", lowered)

    def test_other_posts_are_untouched_bodies(self):
        self.assertIn("Staying off-site?", OFFSITE)
        self.assertIn("Friend joined the trip", MODIFY)
        self.assertNotIn(SLUG, OFFSITE)
        self.assertNotIn(SLUG, MODIFY)


if __name__ == "__main__":
    unittest.main()
