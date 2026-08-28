# Winner implementation spec — Park Day Pulse

## User story

As Craig or Jessica, I land on magictablefinder.com and immediately understand that a precise watch will text me when a matching Walt Disney World dining reservation **newly opens**. I sign in with my existing profile. After login, the working app looks like the same product — not a castle-emoji overlay in front of a different admin tool.

## Files that will change

- `public/index.html` — unauthenticated landing + restyle of post-login chrome
- `design-tournament/SCORE.md` — judging record (already drafted)

Do not change Netlify functions, poller, Gist, Disney session, or alert semantics.

## Acceptance criteria

1. Unauthenticated first screen is a Park Day Pulse landing (navy, Outfit/DM Sans, lime primary CTA, coral for “new opening”). No 🏰 castle in wordmark, login, or post-login `<h1>`.
2. Locked header promise: “SMS when a matching table newly opens.” At ~390px the promise must remain readable (wrap or hide the wordmark mark, do not clip the sentence).
3. Hero headline temperature: “The opening text, not the hunt.” Phone/SMS mock uses the California Grill fixture and STOP/HELP language. Secondary CTA “See how it works” scrolls to `#how`.
4. Landing IA (same as BRIEF): sticky header, hero, `#how` (three locked steps), trust strip, `#proof` (watch card **and** SMS), `#faq` (six required questions), `#signin`, footer.
5. Trust strip: Watches · SMS · Every 10 min · Your phone only (no fake numbers).
6. FAQ answers stay honest: new openings only; signed-in profile’s phone; not official Disney; every 10 minutes; SMS consent at Create Watch; no table guarantee.
7. Sign-in uses existing fields/IDs only: `#login-overlay`, `#login-profile`, `#login-pwd`, `#login-btn`, `#login-error`. Do not introduce `#profile`, `#password`, or `#signin-form` as replacements. Profiles remain Craig and Jessica. Password starts empty. Success still uses `attemptLogin` + `/_api/status`. Do not navigate to `app.html`. Header/hero Sign in scrolls to `#signin`.
8. Footer and sign-in panel link Privacy, Terms, and SMS consent with **relative** paths (`/privacy.html`, `/terms.html`, `/sms-consent.html`).
9. After login, overlay hides; create-watch, restaurant tab, watch list, calendar modal, SMS consent checkbox, trip dates (`#trip-start`, `#trip-end`), and status health still work. Preserve every production DOM ID the existing script binds (do not copy Park Day Pulse mock IDs onto those nodes).
10. Post-login chrome: navy header, lime **only** on primary CTAs (`#create-btn`, `#toggle-date-picker`, `#date-picker-done`, `#login-btn`). Keep `--blue` (or a dedicated `--select`) for selected dates, watched calendar days, active tabs, and chips. Update legend/help copy if those colors change. Owner chip stays. Optional owner callout: “Craig’s watches go to Craig’s phone.”
11. Create-watch hint must not say the calendar is optional. Empty watches: “No watches yet. Create one above.” Status copy must not say “re-seed on VPS.”
12. No React/Vue/Tailwind. No `/_api` contract change. No phone numbers or Gist IDs in the UI.
13. Extracted `public/index.html` script passes `node --check`. Alert semantics unit tests still pass.

## Overlay and login behavior (spec-verify)

- Restyle `#login-overlay` into a **scrollable full-viewport landing** (`overflow-y: auto`). Drop flex-centering around a small `#login-box`. `#login-overlay.hidden` still hides the landing after auth.
- First paint / Lock / 401: show the landing at the **top** (hero). Do **not** auto-focus `#login-pwd` (that jumps past the hero). Focus the password only after the user clicks Sign in or lands on `#signin`.
- 401 mid-session: return to the landing `#signin` panel with the existing error path; do not fake a logged-in app.

## Color tokens (spec-verify)

Do **not** remap global `--blue` to lime. Lime is CTA paint. Selection/watch/tab semantics stay blue (or a named `--select`) so the availability calendar legend does not lie.

## Out of scope

- New user signup, waitlist, billing
- Framework rewrite
- Changing Disney poller / session / Twilio
- Deploy to `main`
