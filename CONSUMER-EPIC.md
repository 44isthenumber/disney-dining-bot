# Epic E1 — Consumer Magic Table Finder

> **Law for every agent on this work.** If a change is not named in the **current slice** file list, do not do it. Do not “while you’re here” Stripe, auth, Gist, poller, or Disney session. Read this file before coding. Product/ops detail stays in `PRODUCT.md`. Delivery loop: `.cursor/skills/deliver/SKILL.md`.

## Promise (does not change)

SMS when a **new matching** Walt Disney World reservation opening appears. Not a dashboard of every open time. Not Disney. Consumers book on Disney’s site with their own account.

## Locked decisions

| ID | Decision |
|---|---|
| D1 | **Billable watch** = one restaurant + party + meal periods + optional time window + one or more dates. Never meter one `watches.json` date row as a paid alert. |
| D2 | **Hybrid billing:** Single Watch (one-time Stripe Checkout `mode=payment`) and Planner (monthly Checkout `mode=subscription`). Same Stripe Customer. Flat Single Watch price — do not charge more because dates are 60 days out. No 3-date cap. |
| D3 | **Identity:** paying consumers log in first, then Checkout. One app `user_id` ↔ one Stripe Customer. Webhooks (plus optional server Session retrieve on return) own active/inactive. Browser `?success=` is not entitlement. |
| D4 | **Craig and Jessica** (`craig`, `Jessica`) are unrestricted internal owners: no Stripe, no cap, no Checkout, no Portal. Private login stays. Webhooks never attach a Customer to these ids. Billing failures never SMS Jessica. |
| D5 | Catalog is Walt Disney World only until a later epic. |
| D6 | Create Watch is the primary job. Availability calendar is supporting, not the home surface. |
| D7 | SMS consent remains an unchecked checkbox on Create Watch. Stripe checkout is not SMS consent. STOP still wins over a paid watch. |
| D8 | Cloud must not seed Disney, SSH to the VPS, run the poller, clear `open_slots.json` / `seen_slots.json`, or put live Stripe/Twilio/Disney secrets in the repo. |

## Drift rules

- Implement **one slice per PR** unless the spec for that PR lists multiple stories.
- Do not add Brunch to the poller, Disneyland, auto-booking, a free SMS tier, or a faster poll interval.
- Do not advertise a minute-level poll interval on the public landing.
- Do not make the Restaurants calendar the default logged-in surface.
- Dollar amounts and the Planner watch cap stay **placeholders** until Craig sets them (cap placeholder: 8–10 concurrent billable watches for consumers).
- Auth, Stripe, Twilio, VPS, Gist cutover, destructive git: high-risk review (Codex). Stay off `main` unless Craig said deploy.

## Current slice

**Slice 1 is the only slice to build now.** Stories US-1.1 through US-1.6. Slices 2–4 are backlog; citing them in a Slice 1 PR is drift.

---

# Slice 1 — Dining selection (build now)

Family app stays on `WATCH_USERS` login. No Stripe. No new user store.

### User story US-1.1 — Typeahead restaurant picker

As Craig or Jessica, I type part of a restaurant name and pick from matches grouped by park so I am not scrolling a 100-row native select.

**AC**

1. Create Watch restaurant control is a combobox (search input + list). Native `<select id="restaurant-select">` remains as the form value holder (required, class `sr-only` or equivalent) so submit JS keeps reading `#restaurant-select`.
2. Typing filters by restaurant name (case-insensitive). Results are grouped by `park`; empty park group is labeled `Other`. Parks sort A–Z; names sort A–Z within a park.
3. Each result shows a short human badge: Character, Signature, Casual, Event, Experience, or Unique — never raw `dining_type` strings like `diningEvent`.
4. Choosing a result (click or keyboard) calls a shared `selectRestaurant(facilityId)` that sets `#restaurant-select`, updates the combobox display name, and calls `applyBookingTypeUI()`.
5. Keyboard: ArrowUp/ArrowDown move highlight, Enter selects, Escape closes the list. Click outside closes the list.
6. Shared `isWatchable(r)` is the only watchable filter (see US-1.4).
7. Extracted `public/index.html` script passes `node --check`.

**Files:** `public/index.html`, `tests/test_dining_selection_contract.py` (new), `tests/test_landing_contract.py` only if an existing assertion would break.

### User story US-1.2 — Create Watch is the job

As a user, after I pick a place I am creating a watch, not browsing an availability board.

**AC**

1. Default HTML and first paint (logged in): **My Watches** tab is `active`, Restaurants is not. Empty copy remains `No watches yet. Create one above.` Tab choice is not persisted; refresh returns to My Watches. After a successful Create Watch, stay on My Watches (existing post-submit switch).
2. Restaurant cards’ primary button is **Watch this**. It calls `selectRestaurant(facilityId)` (combobox + `#restaurant-select` + `applyBookingTypeUI()`), scrolls `#create-watch` into view, and does not open the calendar modal.
3. Cards expose a secondary **See dates** control under the primary button that opens the existing calendar modal.
4. Park filter is single-select chips derived from **watchable** catalog `park` values, sorted A–Z, plus an **All** chip that clears the filter. Free-text cuisine search may remain. Do not require typing `Disney's Hollywood Studios` as the only park filter. `#park-filter` text input is removed.
5. Calendar modal behavior, SMS consent, and POST `/watches` contract are unchanged.

**Files:** `public/index.html`, `tests/test_dining_selection_contract.py`.

### User story US-1.3 — One party size

As a user, I set party size once and Create Watch plus the calendar use it.

**AC**

1. Header `#global-party` (1–6) is removed.
2. `#party-size` (1–20, specialty `max_party_size` still applied) is the only party control. `getPartySize()` reads it. Calendar modal uses that value.
3. `localStorage disneyPartySize` still persists `#party-size`.
4. Create Watch reset after submit restores party from that stored value, not from a missing header select.

**Files:** `public/index.html`, `tests/test_dining_selection_contract.py`.

### User story US-1.4 — Hide incomplete catalog rows

As a user, I never pick a dinner show or event that cannot be booked because `slug` or `booking_url` is empty.

**AC**

1. Shared `isWatchable(r)`: non-empty trimmed `facility_id`, `name`, `slug`, and `booking_url`. Harmony Barber Shop remains watchable.
2. Combobox, card grid, and `#restaurant-select` options all call `isWatchable` (one function, not three copies).
3. `Hoop-Dee-Doo Musical Revue` and `Celebration at the Top - Sip, Savor, Sparkle` as currently indexed (empty slug/booking_url) do not appear.
4. `tests/test_dining_selection_contract.py` asserts: `function isWatchable`, Watch this, See dates, default My Watches tab, no `#global-party`, `getPartySize` reads `#party-size`, and the script contains the Hoop-Dee-Doo / empty-slug omit path via `isWatchable`.

**Files:** `public/index.html`, `tests/test_dining_selection_contract.py`.

### User story US-1.5 — Epic and product notes stay the source of truth

As an agent, I can read why we are building this without inventing billing or auth in Slice 1.

**AC**

1. This file (`CONSUMER-EPIC.md`) exists and lists slices 1–4, locked decisions, and out of scope.
2. `PRODUCT.md` gains a short **Consumer direction** section: hybrid SKUs, billable watch unit (D1), Craig/Jessica unrestricted (D4), competitive steal/reject vs MouseDining and MouseWatcher, and a pointer to this epic. Do not rewrite the live architecture as if Stripe already shipped.
3. `AGENTS.md` Key docs table includes this epic.

**Files:** `CONSUMER-EPIC.md`, `PRODUCT.md`, `AGENTS.md`.

### User story US-1.6 — Gates

**AC**

1. `python3 -m unittest tests.test_alert_semantics tests.test_landing_contract tests.test_dining_selection_contract`
2. Extract the last `<script>` from `public/index.html` and `node --check` it.
3. No edits to `disney_bot.py`, `monitor.py`, `notify.py`, `seed_disney_session.py`, Netlify `api.js` watch/auth contract, Gist, or `.env`.
4. `scripts/smoke_test_api.py` is not required for Slice 1 (API contract unchanged). Run it before any later slice that touches watches or auth.

**Files:** tests listed above; no worker files.

---

# Slice 2 — Consumer identity (backlog)

Do not implement in the Slice 1 PR.

### US-2.1 Magic link for consumers

As a new guest, I sign in with email magic link (session cookie). No public Craig/Jessica profile directory. Phone is collected for SMS, not used as login.

**Files (when opened):** Netlify functions for session + mail, frontend login panel, tests. High-risk: auth.

### US-2.2 Internal owners stay unrestricted

As Craig or Jessica, I still use the private name+password path. Create Watch never send me to Stripe. No watch cap.

**Files (when opened):** entitlement helper used by API + later poller; tests that `craig` / `Jessica` skip Stripe.

### US-2.3 Users do not live in Gist or `WATCH_USERS`

As an operator, consumer accounts and entitlement live in a real store. Gist remains poller health / `open_slots` / `seen_slots` until a later cutover. Do not clear those files.

**Files (when opened):** new store + migration plan in `PRODUCT.md`. High-risk: Gist.

---

# Slice 3 — Stripe hybrid (backlog)

Do not implement in the Slice 1 PR. Prices are placeholders.

### US-3.1 Bind Checkout to the logged-in user

Checkout Session created on the server with `client_reference_id` = `user_id`, `customer` = existing `stripe_customer_id` when present, `customer_email` only on first purchase and equal to session email. Internal users never get a Session.

### US-3.2 Single Watch purchase

As a consumer without live Planner, Create Watch starts Checkout `mode=payment` for one billable watch (D1). Watch stays `pending_payment` until webhook (or server retrieve) marks it paid. Active until last date passes.

### US-3.3 Planner subscription

As a consumer who keeps adding restaurants, I subscribe (`mode=subscription`). While `active` or `trialing`, I create watches in-app under the cap with no per-watch Checkout.

### US-3.4 Entitlement cache

Site stores `stripe_customer_id`, `planner_status`, `planner_subscription_id`, `planner_current_period_end`, `cancel_at_period_end`. Webhooks: `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.paid`, `invoice.payment_failed`. Idempotent on `event.id`. `past_due`: no new watches; existing paid dates keep alerting; CTA is Portal. Poller SMS uses this cache, not the browser.

### US-3.5 Customer Portal

Manage billing exists only if `stripe_customer_id` is set. Portal: card, invoices, cancel at period end. Return URL server-refreshes subscription. Do not enable pause until pause has a watch rule.

### US-3.6 Upgrade prompt

After a second (or third) Single Watch in a trip, show spend vs Planner monthly and offer subscribe Checkout on the same Customer.

### US-3.7 Cancel and STOP

Cancel at period end: no new watches; dates still in the paid period keep alerting. STOP opts out of SMS even if paid.

**Files (when opened):** Netlify Stripe routes, webhook, frontend paywall, entitlement tests, Privacy/Terms Stripe processor language. High-risk: Stripe. Test mode only in Cloud.

---

# Slice 4 — Open signup (backlog)

Public signup only after Slices 2–3. Global active-watch budget so a launch spike cannot stall the 10-minute poller. Still one headed Disney session on the VPS.

---

# Out of scope (all slices unless Craig asks)

- Brunch as a poller meal period
- Disneyland / other parks
- Booking on the guest’s Disney account
- Free email-only tier / free SMS
- Changing `DISNEY_HEADLESS`, recovery cooldown, navigate-per-restaurant, refresh-failure handling
- Advertising poll interval in minutes on the landing
- MouseDining-style public availability calendar as the home screen
- Per-meal party sizes
- Portal pause
- Goose / Claude Code

# Slice 1 files that will change

- `CONSUMER-EPIC.md` (this file)
- `PRODUCT.md`
- `AGENTS.md`
- `public/index.html`
- `tests/test_dining_selection_contract.py` (new)
- `tests/test_landing_contract.py` only if required to keep existing tests green
