# Trusted Watch — Vision Pitch

## Audience

Disney trip planners who have been burned by flaky bots and fan-site dashboards. They need to trust that someone competent is watching for the table — not operating a scraper or browsing a live availability board. Craig and Jessica are the only users; each profile's alerts stay on that person's phone.

## Art direction (type, color, motion)

- **Type:** Figtree throughout — warm humanist sans, clear hierarchy without luxury poetry. Functional labels (Watch, Party, Date, Time window) at 812–9375rem scale; headlines at tight negative tracking.
- **Color:** Elevated current product palette — ink `#1A1A2E`, trustworthy blue `#1A56DB`, health green `#276749`, paper `#F7F8FC`, white cards. Health states use green / amber / red dots with plain-language status text.
- **Motion:** None required. Focus rings, hover borders, and FAQ `<details>` toggles only. Line-diagram icons (watch → poll → SMS) replace photography.

## Why this earns trust

1. **Owner clarity from the first screen** — "Craig's watches go to Craig's phone" in hero steps, sign-in hint, and app header chip. No household dashboard, no per-card owner column.
2. **Health as a real header control** — Last checked time is visible and clickable to preview healthy / needs attention / stale. Proof section shows the same green health line beside a stylized create-watch preview.
3. **Honest alert framing** — FAQ kills the dashboard misconception; trust strip uses locked labels without fake metrics; sample SMS uses the shared California Grill fixture exactly.
4. **SMS consent at Create Watch** — unchecked by default, Create Watch disabled until checked. Sign-in never implies opt-in.
5. **Most usable create-watch** — calendar-first Choose Dates with chips and Done, manual entry secondary, meal checkboxes (Any meal when none checked), optional time window, restaurant datalist with browse as supporting tool only.

## What we would not ship

- Castle emoji, fireworks, sparkles, or official Disney marks
- Live availability calendar as the main surface
- Fake user/table counts or success rates
- Per-card owner columns or cross-profile watch lists
- Scraper / VPS / Akamai language in the UI
- SMS consent at login

## Implementability notes for `public/index.html`

- Restyle the existing post-login SPA chrome: sticky header with owner chip + health line + Lock, white card panels on paper background, Figtree via Google Fonts link (same as today’s font loading pattern).
- Replace the castle login overlay with the landing `index.html` structure — eight locked sections map 1:1 to new unauthenticated DOM; sign-in panel becomes the login form that today’s overlay handles.
- Create-watch tab: adopt calendar-first date chips, meal checkbox group, consent gate on submit button — all achievable in vanilla JS already used in the SPA.
- Watch list cards: show restaurant / dates / party / meal / window / delete; drop any owner column since session is profile-scoped.
- Health widget: three CSS modifier classes on the existing status element; default copy "Last checked 10:42 PM" from production polling timestamp.
- Keep `/_api/*` wiring unchanged; this mock uses static fixtures only for the tournament.
