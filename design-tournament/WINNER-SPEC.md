# Winner implementation spec — Quiet Luxury

Craig picked **Quiet Luxury** as the visual base. Copy in the mock is not gospel — keep the look, use product-honest language.

## User story

As Craig or Jessica, I land on magictablefinder.com and feel a calm, competent product is watching for the table. I sign in with my existing profile. After login, the working app uses the same paper / ink / gold system — not a castle-emoji overlay in front of a blue admin tool.

## Files that will change

- `public/index.html` — unauthenticated landing + restyle of post-login chrome
- `design-tournament/WINNER-SPEC.md` — this spec
- `design-tournament/SCORE.md` — record Quiet Luxury as the picked base
- `tests/test_landing_contract.py` — HTML/JS contract for landing IDs, copy, and no ops jargon

Do not change Netlify functions, poller, Gist, Disney session, or alert semantics.

## Visual system (locked)

- Type: Fraunces headlines, Source Sans 3 UI (Google Fonts + system fallbacks)
- Color: dusk ink `#1C1917`, warm paper `#F6F1E8`, gold `#B0894A`, moss `#3F5C4A`
- Primary CTAs are **ink**, not lime or saturated blue
- Atmosphere: The only fireworks is a cinematic gold wand with champagne-spray pixie dust under the hero CTAs (Craig, 2026-08-31). Header lockup is the same wand at logo scale: an 88×62 star-tip mark (pommel rings, thick shaft, 4-point star, compact dust) beside Fraunces ink “Magic Table Finder” — not a hairline overlay on the M. No plate-rim / candle motif. No castle, no 🏰, no Disney trademarks.
- Headline: **“We monitor the openings.”**
- Subhead: **“We'll text you when your Walt Disney World reservations open up. You log in. You book.”**

## Copy (fix the mock)

Keep Craig’s headline and subhead. Drop hotel/ops jargon from the mock: “The Method,” “bespoke,” “battery remain undisturbed,” “alert semantics,” pre-filled demo password.

Use BRIEF language: Watch, Alert me, Party, Date, Time window, Any meal, Last checked, “SMS when a matching table newly opens.”

## Acceptance criteria

1. Unauthenticated first screen is Quiet Luxury (paper, ink, gold, Fraunces). No 🏰 in wordmark, login, or post-login `<h1>`.
2. Sticky landing header: wordmark, promise **“SMS when a matching table newly opens.”**, Sign in → `#signin`. At ~390px the promise stays readable (wrap or hide the emblem, do not clip the sentence).
3. Hero: “We monitor the openings.” Subhead: “We'll text you when your Walt Disney World reservations open up. You log in. You book.” Primary Sign in → `#signin`. Secondary “See how it works” → `#how`.
4. Landing IA: sticky header, hero, `#how` (three steps in Craig’s natural copy: you select restaurants and dining times; we’ll keep watch for those reservations to open; we send a text with the reservation link when it opens), trust strip (Watches · SMS · Frequent scans · Your phone only), `#proof` (California Grill watch card **and** the shared SMS with STOP/HELP **and** a Book link), `#faq` (six required questions), `#signin`, footer.
5. FAQ answers stay honest: new openings only; signed-in profile’s phone; not official Disney; we scan frequently (do **not** publish a minute interval on the landing — that invites a “we check faster” undercut); SMS consent at Create Watch; no table guarantee.
6. Sign-in uses existing IDs only: `#login-overlay`, `#login-profile`, `#login-pwd`, `#login-btn`, `#login-error`. Do not use mock IDs (`#profile-select`, `#password-input`, `#signin-form` as auth). A wrapping `<form class="signin-box">` without a new auth id is allowed so Sign in submits through `attemptLogin`. Password starts empty. Real `attemptLogin` + `/_api/status`. Do not navigate to `app.html`.
7. Footer and sign-in panel link Privacy, Terms, and SMS consent with relative paths `/privacy.html`, `/terms.html`, `/sms-consent.html`.
8. `#login-overlay` is a **scrollable full-viewport landing**. Drop flex-centering around a small box. `.hidden` still hides it after auth.
9. First paint / Lock: landing at the **top** (hero). Do **not** auto-focus `#login-pwd`. Focus password only after Sign in / `#signin`. 401 returns to `#signin` with the existing error path.
10. After login, overlay hides. Preserve every production DOM ID the script binds (create-watch, tabs, restaurants, watches, calendar modal, trip dates, status). Keep `/_api/*` wiring.
11. Post-login chrome uses paper background, ink header or ink-on-paper header consistent with the landing, gold hairlines, moss for healthy/watching. Primary buttons (`#login-btn`, `#create-btn`, `#toggle-date-picker`, `#date-picker-done`) are dusk ink. **Do not remap `--blue` to gold.** Keep `--blue` (or `--select`) for selected dates, watched calendar days, active tabs, chips. Update legend/help if those colors change.
12. Create-watch hint must not say the calendar is optional. Empty watches: “No watches yet. Create one above.” Status must not say “re-seed on VPS” or expose worker/scrape language.
13. No React/Vue/Tailwind. No phone numbers or Gist IDs.
14. Extracted script passes `node --check`. `python3 -m unittest tests.test_alert_semantics` passes.

## Out of scope

- New user signup, waitlist, billing
- Framework rewrite
- Poller / Disney session / Twilio / Gist
- Deploy to `main`
- Perfecting every line of marketing copy (style is the base; copy can still be tightened later)
