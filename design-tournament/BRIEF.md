# Magic Table Finder — Design tournament shared brief

This is a **vision bake-off**, not a production ship. Three teams present competing looks for the same product. Craig scores them. The winner is then implemented into `public/index.html` on a feature branch (not `main`).

## Product

Magic Table Finder is a private Walt Disney World dining alert tool for Craig and Jessica. They create precise watches. A VPS worker polls every 10 minutes. When a **new matching** reservation opening appears, the watch owner gets an SMS. Continuously open times stay quiet.

Live site today: [magictablefinder.com](https://magictablefinder.com) — a functional ops SPA with a castle-emoji login overlay. No marketing landing exists.

This round is a **public confidence landing + sign-in**, still gating the existing family app. No waitlist, signup, billing, or extra users.

## Emotional job

A Disney trip planner should feel *someone competent is watching for the table*, not that they are operating a scraper.

## Locked product truth (all teams)

- Promise: SMS when a **new matching** reservation opens. Not a live board of every open time.
- CTA: **Sign in**. Profiles are Craig and Jessica. Alerts go to that profile's phone.
- Footer must link to `/privacy.html`, `/terms.html`, and `/sms-consent.html`.
- Not Disney. No official marks, no castle-as-logo, no “Disney dining reservations guaranteed,” no Mouse ears as brand.
- Copy may say “Disney World dining” / “Walt Disney World restaurants” as the domain. Do not impersonate Disney Parks.
- Mobile-first. Hero must work on a phone.
- Vanilla HTML/CSS/JS only. No React, Vue, Tailwind CDN, or other frameworks.
- Do not wire mocks to production APIs (`/_api/*`). Static demo data only.
- Do not invent metrics (“12,481 tables booked”). Proof must be qualitative or honestly framed as sample watches.
- Watch creation fields that must appear in the logged-in mock: restaurant, party size, one or more dates (calendar-first `Choose Dates` + `Done`, manual entry secondary), meal period (Breakfast / Lunch / Dinner / any meal), optional earliest/latest time, unchecked SMS consent checkbox, `Create Watch`.
- Owner chip (Craig or Jessica) and bot health (last checked, healthy / needs attention / stale) must be visible when logged in.
- Do not show phone numbers, Gist IDs, facility IDs, tokens, or “scrape / config / HTTP 404”.

## Information architecture (same for every team)

### Landing (`index.html`)

1. Sticky header: wordmark, one-line promise, Sign in
2. Hero: headline, subhead, primary Sign in, secondary “See how it works”
3. How it works: exactly three steps
4. Trust strip: watches, SMS, 10-minute poll, owner-scoped alerts
5. Proof: sample watches / sample SMS moment — no fake stats
6. FAQ: 4–6 questions that kill doubt (new vs all openings, whose phone, not official Disney, SMS consent, poll cadence)
7. Sign-in panel: profile select (Craig / Jessica), password, Sign in, legal links
8. Footer: Privacy, Terms, SMS consent

### Logged-in chrome (`app.html`)

Mock of the working product in this vision’s visual system:

- Header: wordmark, owner chip, health (“Last checked 10:42 PM”), Lock
- Create Watch as the primary job
- Watch list with restaurant, dates, party, meal/window, owner, delete
- Empty state copy if you show an empty variant: “No watches yet. Create one above.”
- Optional restaurant browse as a supporting tool, not the hero

### Pitch (`PITCH.md`)

One page: audience, art direction (type, color, motion), why this earns trust, what we would *not* ship.

## Technical constraints

- Self-contained files under `design-tournament/<team-slug>/`
- `index.html` and `app.html` must open from a static server with no build step
- System fonts or Google Fonts via `<link>` only (no npm)
- Images: CSS gradients, inline SVG, or unsplash/placeholder textures that are **not** Disney park photography or copyrighted characters
- Sign in on the landing may navigate to `app.html` (no real auth)
- Keep CSS inside the HTML files or a local `styles.css` in the team folder

## What “badass confidence” means here

Confidence is: *I will not miss Be Our Guest at 7:15 for a party of 4.*  
Confidence is not: neon, fireworks, or a dashboard of every open table.

Avoid:

- Scraper / bot / worker / Akamai language
- Guarantees you cannot keep
- Official Disney visual language
- Fake social proof
