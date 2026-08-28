# Winner implementation spec — Park Day Pulse

## User story

As Craig or Jessica, I land on magictablefinder.com and immediately understand that a precise watch will text me when a matching Walt Disney World dining reservation **newly opens**. I sign in with my existing profile. After login, the working app looks like the same product — not a castle-emoji overlay in front of a different admin tool.

## Files that will change

- `public/index.html` — unauthenticated landing + restyle of post-login chrome
- `design-tournament/SCORE.md` — judging record (already drafted)

Do not change Netlify functions, poller, Gist, Disney session, or alert semantics.

## Acceptance criteria

1. Unauthenticated first screen is a Park Day Pulse landing (navy, Outfit/DM Sans, lime primary CTA, coral for “new opening”). No 🏰 castle in wordmark or login.
2. Locked header promise: “SMS when a matching table newly opens.”
3. Hero headline temperature: “The opening text, not the hunt.” Phone/SMS mock uses the California Grill fixture and STOP/HELP language.
4. How-it-works is the three locked steps in order.
5. Trust strip: Watches · SMS · Every 10 min · Your phone only (no fake numbers).
6. FAQ covers the six required questions with honest answers (new openings only; signed-in profile’s phone; not official Disney; every 10 minutes; SMS consent at Create Watch; no table guarantee).
7. Sign-in uses existing fields/IDs: `#login-profile`, `#login-pwd`, `#login-btn`, `#login-error`. Profiles remain Craig and Jessica. Password is empty by default. Success still uses existing `attemptLogin` / `/_api` auth. Header/hero Sign in scrolls to `#signin`.
8. Footer links Privacy, Terms, SMS consent (`/privacy.html`, `/terms.html`, `/sms-consent.html`).
9. After login, overlay hides; create-watch, restaurant tab, watch list, calendar modal, SMS consent checkbox, and status health still work.
10. Post-login chrome uses the same visual system: navy header, lime primary buttons (`Create Watch`, `Choose Dates`, `Done`), owner chip, status dot colors for ok/warn/err/stale.
11. No React/Vue/Tailwind. No `/_api` contract change. No phone numbers or Gist IDs in the UI.
12. Extracted `public/index.html` script passes `node --check`. Alert semantics unit tests still pass.

## Out of scope

- New user signup, waitlist, billing
- Framework rewrite
- Changing Disney poller / session / Twilio
- Deploy to `main`
