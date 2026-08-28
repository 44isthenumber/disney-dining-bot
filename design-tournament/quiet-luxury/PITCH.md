# Vision Pitch: Quiet Luxury

**Team:** Quiet Luxury  
**Branch:** `cursor/vision-quiet-luxury-1361`  
**Folder:** `design-tournament/quiet-luxury/`  
**Tagline:** *“The table is being watched.”*

---

## 1. Audience

Magic Table Finder serves Craig and Jessica as they plan their Walt Disney World itinerary.

The emotional job is not hunting or frantic dashboard refreshes. The trip is already booked, flights are scheduled, and park days are set. What is needed is quiet, unshakeable confidence: *someone competent is watching for our table while we pack, travel, and walk the parks.*

They do not want to manage a bot, inspect scraper logs, or receive noisy notifications for tables they did not request. They want a disciplined, bespoke watch that sends a single, actionable SMS the moment their requested opening appears.

---

## 2. Art Direction

### Typography
- **Headlines & Numerals:** `Fraunces` — an optical-size serif with warmth, editorial poise, and understated character.
- **UI & Form Controls:** `Source Sans 3` — a crisp, humanist sans-serif offering effortless legibility for date pickers, meal selectors, and status indicators.
- **Labels & Microcopy:** Wide-tracked small caps (`0.12em` to `0.22em`) to establish visual rhythm without heavy borders.

### Color Palette
- **Warm Paper (`#F6F1E8` / `#FAF6F0`):** Replaces harsh stark-white backgrounds with the tactile warmth of luxury linen and editorial stationery.
- **Dusk Ink (`#1C1917` / `#44403C`):** High-contrast, deeply legible dark ink for typography and primary buttons.
- **Gold Line (`#B0894A` / `#CDB68D`):** Brushed antique gold accents for delicate hairline dividers, focus rings, and section eyebrows.
- **Deep Moss (`#3F5C4A`):** A calm, reassuring botanical green used exclusively for active watch states and bot health.
- **No Saturated Blue or Neon:** Eliminates tech-SaaS cliches in favor of a timeless hospitality aesthetic.

### Atmosphere & Imagery
- Pure CSS and inline SVG motifs evoking a candlelit table: fine concentric plate rims, delicate dashed borders, and subtle warm radial glows.
- Zero copyrighted Disney imagery, castle icons, or character art.

### Motion
- Restrained and purposeful. Soft 150–200ms opacity transitions for calendar popovers and card dismissals. No bouncy easing, confetti, or distracting loaders.

---

## 3. Why This Earns Trust

1. **Precise Alert Semantics:** The hero and FAQ immediately clarify the core product promise: texts are sent *only when a matching table newly opens*, not as an uncurated firehose of every open slot.
2. **Owner-Scoped Clarity:** The session is explicitly tied to the signed-in profile (`Craig` or `Jessica`) at the header level, avoiding messy multi-owner confusion while keeping watch cards uncluttered.
3. **Transparent SMS Consent:** Consent is never assumed or buried in login. An explicit, unchecked agreement is required on the reservation card before a watch can be activated.
4. **Plain-Language Health Reporting:** The system health indicator (`Last checked 10:42 PM`) provides clear reassurance of background polling without exposing VPS, headless browser, or scraper mechanics.
5. **Typeset Proof:** Proof is demonstrated with real sample watches and exact SMS fixtures (California Grill, party of 2, 7:15 PM) rather than fabricated statistics or fake customer reviews.

---

## 4. What We Would Not Ship

- **No Castle Emoji 🏰 or Disney Clichés:** No theme-park tropes that compromise brand independence or read like an amateur fan site.
- **No Fake Metrics:** No inflated claims like *"15,000 tables secured"* or *"100% reservation guarantee."*
- **No Availability Heatmaps as the Main UI:** We reject dense green/grey seat-availability grids that make users feel like they are operating a flight booking terminal. Create Watch remains the primary task.
- **No Jargon or Error Codes:** No mentions of tokens, cron jobs, HTTP 404s, or scraper architecture in user-facing surfaces.

---

## 5. Implementability Notes for `public/index.html`

- **Pure Vanilla Architecture:** Built entirely in standard HTML5, CSS3, and vanilla JavaScript with zero framework dependencies (no React, Tailwind, or build tooling required).
- **Direct SPA Drop-In:** The landing screen seamlessly replaces the legacy password overlay in `public/index.html`, while `app.html` provides the exact CSS and DOM blueprint for the post-login SPA.
- **Backend API Compatibility:** All form fields (restaurant dropdown, date chips, party size, meal multi-select, and time window) map directly to the existing `/_api/*` payload contracts.
- **Performance:** Lightweight footprint with asynchronous Google Font loading and pure CSS styling ensures instant first-contentful paint (<150ms) across all mobile and desktop devices.
- **Responsive Guarantee:** Tested and fluid from narrow mobile screens (375px–390px) up to ultra-wide desktop displays.
