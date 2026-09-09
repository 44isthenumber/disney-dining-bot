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
- Atmosphere: The only fireworks is a cinematic gold wand with champagne-spray pixie dust under the hero CTAs (Craig, 2026-08-31). Header is quieter: a diagonal gold wand sits to the **left** of the capital M, tip near the M’s top-left corner, with pixie dust sprinkling from the tip onto the letter. Not a standalone mark and not a shaft drawn across the M. No plate-rim / candle motif. No castle, no 🏰, no Disney trademarks.
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

## Addendum — Landing pop restyle (2026-09-02)

Approved extension of the Quiet Luxury base. Material layer: paper grain (`feTurbulence` at ~3.5% opacity), warm gold vignette behind the hero, ink-tinted elevation tokens (`--shadow-1/2/3`), and gold hairlines (`--hairline`) on landing and app cards. Hero “moment stage”: the cinematic wand remains the only fireworks; a sample text card (`.mtf-text.hero-text`) sits at the end of the wand’s dust trail. Motion is one-time and gated (`prefers-reduced-motion` + `IntersectionObserver` → `html.mtf-motion`): wand shaft draw-on, text-card arrival, and scroll reveals. FAQ items are `<details>` accordions. Planner is the one ink high-contrast card. How-it-works uses a gold hairline rail. No new sparkle, no status-dot pulse.

## Addendum — Conversion hero (2026-09-02, approved by Craig)

Replaces the locked headline and subhead above. Headline: **"Sold out? We'll text you the moment a table opens."** Subhead explains the mechanism and states that booking happens on Disney's site on the guest's own account. Pricing leaves the subhead; it lives in a note under the CTA and in `#pricing`. Desktop hero is two columns: copy and a guest starter (WHERE restaurant + WHEN dates + WHO party + CTA, with quick-start chips for hard-to-get tables) on the left, the wand landing on the sample text on the right. WHO (party chips 1–8, default Party of 2) is always visible above the CTA. Meal, time window, phone, email, and text consent appear after Start my watch with restaurant, dates, and party (`#create-watch.is-collapsed`); date selection alone does not expand those fields. The consent gate and Stripe handoff are unchanged. CTA copy: "Start my watch · from $4.99" / "Start my watch · $4.99" (never "Continue to payment"). The signed-in app form uses the same WHO control. An ink-background hero was tried and rejected the same day; the hero stays paper.

## Addendum — Category H1 (Option 2, Helm/Craig)

**Supersedes** the Conversion hero addendum for H1 / immediate-sub assignment only. `.lead`, trust strip, guest starter, wand, and paper hero stay.

- **H1** = `Walt Disney World dining alerts` — same category phrase as `<title>` / `og:title` / `twitter:title` (`Walt Disney World dining alerts | Magic Table Finder`). Do not shorten to “Disney World dining alerts.”
- **Immediate sub** (`.l-hero-sub`, not a second H1) = `Sold out? We'll text you the moment a table opens.` Still prominent serif/ink; clearly secondary to the H1.
- Remove the gold hero eyebrow that whispered the same category phrase. Other section eyebrows (How it works, Pricing, Sample text, Sign in) stay.
- Do not leave two competing on-page versions of the dining-alerts phrase.

## Addendum — Phase 1 Quiet Luxury identity (2026-09-07)

Craig locked the production identity. This addendum **supersedes** the Visual system type, hexes, and 5-point star wand above for anything shipped in `public/`.

- Jewelry wand only: pommel · tapered shaft · lozenge tip · gold dust. Canonical SVG: `public/brand/mark.svg`. Favicon weight: `public/brand/favicon.svg`.
- Not a 5-point Disney star, Mickey ears, castle, or CSL red (`#EF0107`).
- Tokens: cream `#f5f1e9`, gold `#aa8b54`, ink `#000000`, paper `#ffffff`, plus `--mtf-*` in `public/index.html`.
- `--paper` is the cream page ground (`var(--mtf-cream)`). `--paper-card` / `--mtf-paper` is white card surface.
- Wordmark: Playfair Display, ink. Body: Inter / system sans. Gold is never a CTA flood fill. `--blue` stays for selected dates, tabs, and chips.
- Header lockup is gold wand + Playfair “Magic Table Finder” on cream. OG card: `public/og-1200x630.png`.
