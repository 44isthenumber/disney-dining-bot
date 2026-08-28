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
- Footer must link to the live Privacy, Terms, and SMS consent URLs listed in the landing IA.
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

Do not invent extra landing sections. Do not omit these. Visual treatment may differ; structure may not.

### Landing (`index.html`)

1. Sticky header: wordmark, locked one-line promise **“SMS when a matching table newly opens.”**, Sign in (anchor `#signin`)
2. Hero: headline, subhead, primary Sign in (`#signin`), secondary “See how it works” (`#how`)
3. How it works (`#how`): exactly these three steps, in this order — (1) Create a precise watch (2) We check every 10 minutes (3) SMS only when a matching time newly opens
4. Trust strip: four labels, no numbers — Watches · SMS · Every 10 min · Your phone only
5. Proof (`#proof`): both a sample watch card **and** a sample SMS using the shared fixtures below
6. FAQ (`#faq`): the six questions in Shared FAQ, answers in your voice
7. Sign-in panel (`#signin`): profile select (Craig / Jessica), password field, Sign in button, legal links. Submitting **does not authenticate**. It navigates to `app.html?profile=craig` or `?profile=Jessica` (use the selected name). Header/hero Sign in only scrolls here. Do not imply SMS opt-in at login — consent happens on Create Watch.
8. Footer: Privacy, Terms, SMS consent — use live URLs so a team-folder static server does not 404:
   - `https://magictablefinder.com/privacy.html`
   - `https://magictablefinder.com/terms.html`
   - `https://magictablefinder.com/sms-consent.html`

### Logged-in chrome (`app.html`)

Mock of the working product in this vision’s visual system. Open already signed in as the `profile` query param (default Craig). Lock returns to `index.html`.

- Header: wordmark, owner chip (the signed-in name only), health line, Lock
- Health must be distinguishable in three states. Default demo: healthy — **“Last checked 10:42 PM”**. Include a small control or three static examples so judges can see needs-attention and stale treatments (plain language, no VPS / re-seed / scrape copy).
- Create Watch is the primary job, above the fold on desktop, first on mobile. Do not default to a restaurant browser.
- Watch list: restaurant, dates, party, meal/window, delete. **Do not put an owner column on each card** — the session is already owner-scoped; the header chip is enough.
- Empty-state copy if shown: **“No watches yet. Create one above.”**
- Meal period: multi-select (checkboxes or pills that behave like checkboxes). Leave all unchecked = Any meal. Not a single-select radio.
- Dates: calendar-first. Button **Choose Dates**, selected chips, **Done**, **Enter dates manually** as secondary. Do not tell people the calendar is optional.
- SMS consent: explicit **unchecked** checkbox with the consent language in Shared fixtures. Create Watch is disabled until it is checked (mock JS is enough).
- Optional restaurant browse as a supporting tool, not the hero. **Do not** mock a green/grey availability calendar as the main surface — that reads as an availability dashboard.

### Sign-in and merge contract

Production today is one SPA (`public/index.html`) with a full-screen login overlay, then create-watch + restaurant tabs + watch list.

Tournament mapping for the later `/deliver` pass:

| Mock | Production target |
|---|---|
| `index.html` landing | **New** unauthenticated first screen. Replaces the castle-emoji overlay as the public face. Sign-in panel becomes the login UI. |
| `app.html` | Visual direction for **post-login chrome** of the existing SPA: header, create-watch, watch list, health. Keep `/_api/*` wiring. Do not require a framework rewrite. |
| Not in mock scope | Trip-date header fields, restaurant availability calendar modal, live API, real passwords |

### Shared fixtures (all teams use these)

**Craig session:** one watch card — California Grill · party 2 · Sep 18, 2026 · Dinner · 7:00–8:30 PM  
**Jessica session:** one watch card — Space 220 · party 4 · Sep 19–20, 2026 · Any meal  
**Landing proof** always uses the Craig / California Grill watch plus this SMS:  
`California Grill opened Sat 9/18, 7:15 PM, party of 2. Reply STOP to opt out. Reply HELP for help.`  
**SMS consent checkbox copy:**  
“I agree to receive SMS alerts from Magic Table Finder when matching Disney dining reservation openings are found. Message frequency varies based on my watch activity and reservation availability. Message and data rates may apply. Reply STOP to opt out. Reply HELP for help.” Plus Privacy and Terms links (live URLs).  
Do not invent counts of users, tables, or success rates.

### Shared FAQ (required questions)

1. Do you text every open table?  
2. Whose phone gets the alert?  
3. Is this an official Disney product?  
4. How often do you check?  
5. When do you ask for SMS consent?  
6. What if nothing opens?

Answers must stay honest: new matching openings only; the signed-in profile’s phone; no, independent; every 10 minutes; unchecked checkbox at Create Watch, not at login; you wait — we do not guarantee a table.

### Pitch (`PITCH.md`)

Required sections: Audience · Art direction (type, color, motion) · Why this earns trust · What we would not ship · Implementability notes for `public/index.html`.

## Technical constraints

- Self-contained files under `design-tournament/<team-slug>/`
- `index.html` and `app.html` must open from a static server with no build step
- System fonts or Google Fonts via `<link>` only (no npm)
- Images: CSS gradients, inline SVG, or unsplash/placeholder textures that are **not** Disney park photography or copyrighted characters
- Keep CSS inside the HTML files or a local `styles.css` in the team folder
- Do not copy production’s 🏰 castle emoji into wordmark or login
- `PITCH.md` required sections: Audience · Art direction (type, color, motion) · Why this earns trust · What we would not ship · Implementability notes for `public/index.html`

## What “badass confidence” means here

Confidence is: *I will not miss Be Our Guest at 7:15 for a party of 4.*  
Confidence is not: neon, fireworks, or a dashboard of every open table.

Avoid:

- Scraper / bot / worker / Akamai language
- Guarantees you cannot keep
- Official Disney visual language
- Fake social proof
