"""Off-site 60-day head-start blog post stays on the locked draft."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POST = (ROOT / "public/blog/disney-dining-off-site-60-day-head-start.html").read_text(encoding="utf-8")
INDEX = (ROOT / "public/blog/index.html").read_text(encoding="utf-8")
MODIFY = (ROOT / "public/blog/disney-dining-modify-party-size.html").read_text(encoding="utf-8")
WEEK = (ROOT / "public/blog/disney-dining-week-out-recovery.html").read_text(encoding="utf-8")

TITLE = "Staying off-site? Why your Disney dining table was gone at 6 AM on day 60"
DESCRIPTION = (
    "Disney Resort guests can book up to 10 nights at 60 days out; "
    "off-site guests book one day at a time. Why a table can be gone at 6 AM, and what to do."
)
SLUG = "disney-dining-off-site-60-day-head-start"
CRT = "https://magictablefinder.com/alerts/cinderellas-royal-table"
WEEK_HREF = "/blog/disney-dining-week-out-recovery"
MODIFY_HREF = "/blog/disney-dining-modify-party-size"
FAQ_ADVANCE = "https://disneyworld.disney.go.com/faq/dining-reservations/advance-reservations/"
PLAN_TIME = "https://plandisney.disney.go.com/question/time-book-dining-reservations-days-640075/"
PLAN_OFFSITE = "https://plandisney.disney.go.com/question/staying-off-property-reservations-including-dining-577870/"
PLAN_CRT = "https://plandisney.disney.go.com/question/book-dining-reservation-cinderellas-castle-day-advance-646572/"
PLAN_NARCO = "https://plandisney.disney.go.com/question/dining-reservation-narcoosees-grand-floridian-without-560188/"
PLAN_GRACE = "https://plandisney.disney.go.com/question/grace-period-regarding-dining-reservations-time-cancel-525702/"
FAQ_CANCEL = "https://disneyworld.disney.go.com/faq/dining-reservations/restaurant-reservation-cancellation/"
CRT_PAGE = "https://disneyworld.disney.go.com/dining/magic-kingdom/cinderella-royal-table/"


class BlogOffSite60DayHeadStartTest(unittest.TestCase):
    def test_post_title_meta_and_canonical(self):
        self.assertIn(f"<title>{TITLE} | Magic Table Finder</title>", POST)
        self.assertIn(f"<h1>{TITLE}</h1>", POST)
        self.assertIn(f'content="{DESCRIPTION}"', POST)
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
        self.assertIn('datetime="2026-10-28"', POST)
        self.assertIn("October 28, 2026", POST)
        self.assertIn('<p class="blog-kicker"><a href="/blog">Blog</a></p>', POST)
        self.assertIn('<article class="blog-article">', POST)

    def test_index_lists_this_post_first(self):
        self.assertIn('rel="canonical" href="https://magictablefinder.com/blog"', INDEX)
        self.assertIn(f'href="/blog/{SLUG}"', INDEX)
        self.assertIn(TITLE, INDEX)
        self.assertIn("October 28, 2026", INDEX)
        self.assertLess(INDEX.index(f"/blog/{SLUG}"), INDEX.index(MODIFY_HREF))
        self.assertLess(INDEX.index(MODIFY_HREF), INDEX.index(WEEK_HREF))
        self.assertEqual(INDEX.count("<h1>"), 1)

    def test_locked_draft_sections_and_math(self):
        self.assertIn("<h2>The rule, in Disney’s words</h2>", POST)
        self.assertIn("<h2>Why that can beat you to a table</h2>", POST)
        self.assertIn("<h2>A case that looks the same</h2>", POST)
        self.assertIn("<h2>What you can still do yourself</h2>", POST)
        self.assertIn("<h2>If you’d rather not refresh all week</h2>", POST)
        self.assertEqual(POST.count("<h2>"), 5)
        self.assertIn("up to a 10-night stay", POST)
        self.assertIn("book each day individually as its own 60-day window arrives", POST)
        self.assertIn("approximately 6:00 AM daily for select restaurants", POST)
        self.assertIn("A resort guest checks in March 1 for a 10-night stay", POST)
        self.assertIn("At 6 AM on December 31", POST)
        self.assertIn("March 1 through March 10", POST)
        self.assertIn("Your window opens on January 9, which is nine days later", POST)
        self.assertIn("This is the usual explanation, not a certainty.", POST)
        self.assertIn("your next hotel’s window opens off <em>its</em> check-in date", POST)
        self.assertNotIn("<h2>Sources", POST)
        self.assertNotIn("FACT_GATE", POST)
        self.assertNotIn("**Status:**", POST)
        self.assertNotIn("NOT published", POST)

    def test_citation_links_once_each(self):
        for url in (
            FAQ_ADVANCE,
            PLAN_TIME,
            PLAN_OFFSITE,
            PLAN_CRT,
            PLAN_NARCO,
            PLAN_GRACE,
            FAQ_CANCEL,
            CRT_PAGE,
        ):
            self.assertEqual(POST.count(url), 1, url)

    def test_crt_is_the_only_money_url(self):
        self.assertEqual(POST.count(CRT), 1)
        self.assertIn(">Watch Cinderella’s Royal Table — Single Watch, $4.99</a>", POST)
        self.assertNotIn("/alerts/space-220", POST)
        self.assertNotIn("/alerts/ohana", POST)
        self.assertNotIn("/alerts/california-grill", POST)
        self.assertNotIn("Planner", POST)
        self.assertNotIn("$14.99", POST)
        self.assertNotIn("/#pricing", POST)
        self.assertNotIn('/#signin">', POST.split("<main", 1)[1])
        self.assertIn("Single Watch is $4.99", POST)

    def test_one_internal_recovery_link(self):
        self.assertEqual(POST.count(WEEK_HREF), 1)
        self.assertIn(">week-out recovery guide</a>", POST)
        self.assertNotIn("/blog/disney-dining-modify-party-size", POST)
        self.assertNotIn("/blog/disney-dining-party-size-traps", POST)
        self.assertNotIn("/blog/cinderellas-royal-table-wrong-date-party-of-5", POST)

    def test_hard_non_claims_stay_out_of_the_public_post(self):
        lowered = POST.lower()
        self.assertNotIn("reddit", lowered)
        self.assertNotIn("disboards", lowered)
        self.assertNotIn("the moment", lowered)
        self.assertNotIn("the second", lowered)
        self.assertNotIn("instantly", lowered)
        self.assertNotIn("dining package", lowered)
        self.assertNotIn("#1", POST)
        self.assertNotIn("angle 1", lowered)
        self.assertNotIn("guaranteed", lowered)
        self.assertIn("We watch; you book.", POST)
        self.assertIn("We can’t promise a table will open.", POST)
        self.assertIn("independent and not affiliated with Disney", POST)

    def test_other_posts_are_untouched_bodies(self):
        self.assertIn("Friend joined the trip", MODIFY)
        self.assertIn("Your hard Disney dining table is gone a week out", WEEK)
        for other in (MODIFY, WEEK):
            self.assertNotIn(SLUG, other)
            self.assertNotIn(PLAN_OFFSITE, other)
            self.assertNotIn(FAQ_ADVANCE, other)
