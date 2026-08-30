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

**Slice 3 is the only slice to build now.** Stories US-3.1 through US-3.7. Slices 1–2 are shipped on `main` (identity + dining selection). Slice 4 is backlog. Do not open public marketing, change the poller, or merge to `main` unless Craig said deploy.

---

# Slice 3 — Stripe hybrid (build now)

Logged-in consumers can **pay for one billable watch** (Single Watch) or **subscribe to Planner**, then get live SMS watches. Craig and Jessica stay unrestricted. Cloud tests inject a fake Stripe client. Never put `STRIPE_*` values in git or Cloud secrets.

## Builder contract (read before coding)

### Law: unpaid watches never reach Gist

The VPS poller SMS-alerts every matching row in `watches.json`. **Do not write a consumer watch to Gist until payment is confirmed** by webhook or by server-side Checkout Session retrieve. Do not add `pending_payment` rows to `watches.json`. Do not change `disney_bot.py`, `watch_store.py`, or `notify.py`.

Store the unpaid payload in Netlify Blobs (`mtf-users`) keyed `checkout:<session_id>`. Stripe metadata is too small for a full watch JSON. Metadata holds `user_id`, `sku`, and for `single_watch` sessions a short `billable_id` (UUID/hex — not watch JSON).

### Entitlement (replaces Slice 2 always-402 for consumers)

`canCreateWatch(user, opts?)` with `opts.activeBillableCount` for cap:

| User | Result |
|---|---|
| missing | 401 `auth` |
| internal (`craig` / `Jessica` / `kind=internal`) | `{ ok: true, code: 'internal' }` — never Stripe |
| consumer `planner_status` `active` or `trialing`, `cancel_at_period_end` false, count `<` cap | `{ ok: true, code: 'planner' }` — POST writes Gist (201) |
| consumer `planner_status` `active` or `trialing`, `cancel_at_period_end` true | `{ ok: false, code: 'canceling', status: 402 }` — no new watches; existing Gist dates keep alerting |
| consumer `planner_status` `past_due` | `{ ok: false, code: 'past_due', status: 402 }` — no new watches; CTA is Portal; existing Gist dates keep alerting |
| consumer at Planner cap | `{ ok: false, code: 'planner_cap', status: 402 }` |
| consumer otherwise (`planner_status` `none` / `canceled`) | `{ ok: true, code: 'single_watch' }` — POST does **not** write Gist; starts Checkout |

`publicIdentity` stays additive. Include: existing fields, `can_create_watch` (true iff `canCreateWatch.ok` **and** Stripe is configured when the mode needs it), `planner_status`, `cancel_at_period_end`, `has_stripe_customer`, `billing_mode` (`internal` \| `planner` \| `single_watch` \| `blocked`), `upgrade_prompt` (true when `single_watch_count >= 2` and not on live Planner). If `STRIPE_SECRET_KEY` or `STRIPE_PRICE_SINGLE_WATCH` is unset, consumers in `single_watch` mode become `blocked` / `billing_unavailable` (`can_create_watch` false). Planner mode still needs `STRIPE_PRICE_PLANNER` only for `/billing/checkout`, not for in-app 201 writes.

Cap: `PLANNER_WATCH_CAP` env, default **8**. Count **billable watches** (D1), not `watches.json` date rows. Each paid Create Watch stamps one `billable_id` on every date row it writes. Count distinct `billable_id` for that `owner_id` where any date is still active (`isActiveWatch`). Missing `billable_id` does not count toward the consumer cap.

### Stripe client (injectable)

New `netlify/functions/stripe_billing.js`. `setStripeForTests(client)` in that file. **`api.js` exports `setWatchWriterForTests(fn)`** (default `saveWatches`) so `tests/test_consumer_auth_api.js` can assert zero Gist writes on checkout and one write on planner 201. Webhook apply uses the same injected writer. Production uses `new Stripe(process.env.STRIPE_SECRET_KEY)` only when that env is set. **Tests never call Stripe’s network.**

Env (Netlify only, never git): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_SINGLE_WATCH`, `STRIPE_PRICE_PLANNER`, optional `PLANNER_WATCH_CAP`. If secret or the needed price id is missing: HTTP **503** `{ code: 'billing_unavailable', detail: 'Paid watches are not available yet.' }` — never leak Stripe config JSON.

### Checkout Session rules (US-3.1)

Created only for a **consumer** session identity (cookie). Internal `X-User-Id` / `X-API-Secret` → **403** `{ code: 'internal_no_stripe' }` on `/billing/checkout`, `/billing/portal`, and on consumer Checkout from `POST /watches`.

Session fields:

- `client_reference_id` = app `user_id` (never `craig` / `Jessica`)
- `customer` = existing `stripe_customer_id` when set
- `customer_email` = session email **only** when `stripe_customer_id` is absent (never send both `customer` and `customer_email`)
- `metadata.user_id`, `metadata.sku`
- `success_url` = `{origin}/?paid=ok&session_id={CHECKOUT_SESSION_ID}`
- `cancel_url` = `{origin}/?paid=cancel`
- `client_reference_id` and metadata `user_id` must match the logged-in user

Origin: `process.env.URL` or `https://magictablefinder.com`.

### POST `/watches` (consumers)

1. Validate the watch body with the **same** 422 rules as today (restaurant, party, dates, meals, times).
2. Consumers **must** send `sms_consent: true`. Missing/false → **422** `{ detail: 'Please confirm text consent so we can send reservation alerts.' }` and **zero** Checkout + **zero** Gist. Stripe is not consent (D7). Internal users do not need this field.
3. Consumers with no `phone` on the user record → **422** `{ code: 'phone_required', detail: 'Add a phone number so we can text you.' }` before Checkout.
4. Load Gist watches for `user.id`, count distinct `billable_id` with at least one active date (`isActiveWatch`). Pass as `opts.activeBillableCount` to `canCreateWatch`. If `activeBillableCount` is omitted when planner cap applies, treat as **fail closed** (`planner_cap` / 402).
5. Then `canCreateWatch(user, { activeBillableCount })`. If not ok → 402 with `code`, `detail`, `can_create_watch: false`, and `portal_url` omitted (Portal is a separate POST).
6. If `code === 'planner'` → write Gist date rows with a new `billable_id`, `recipient_phone` = current `user.phone`, **201** `{ added }` as today.
7. If `code === 'single_watch'` → mint one `billable_id` for this billable watch, then create Checkout `mode=payment` with `STRIPE_PRICE_SINGLE_WATCH` (one line item, flat, quantity 1 — do not multiply by date count). Persist pending payload at `checkout:<session.id>` including the validated watch, `sms_consent: true`, `user_id`, and the same `billable_id`. Put that `billable_id` in Session metadata. **Do not call `saveWatches`.** Return **402** `{ code: 'checkout_required', checkout_url, can_create_watch: true, detail: 'Pay to start this watch.' }`.
8. Shared frontend `postWatch(body)` performs `fetch('/_api/watches', …)` (not generic `apiFetch`). On **402** with `code === 'checkout_required'` and `checkout_url`, call `window.location.assign(checkout_url)` and return (no throw). Other errors surface in UI. `apiFetch` may remain throw-on-error for other routes.

Internal POST `/watches` remains 201/422/500 as today. Never Checkout. Never `sms_consent` requirement.

### Webhooks (US-3.4)

`POST /_api/billing/webhook` is a **public path** (no session cookie, no `X-API-Secret`). Handle it in `exports.handler` **after** `connectBlobsFromEvent` and **before** `resolveIdentity` (same band as `/auth/magic-link`). Verify `Stripe-Signature` against the **raw** body (`event.body`, base64-decode if `isBase64Encoded`) via `stripe.webhooks.constructEvent`. Invalid signature → **400**. Do not `JSON.parse` before verify.

Handled types: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`. Unknown types → 200 no-op.

Idempotent on `event.id`: claim a blob key `stripe_event:<event.id>` (reuse `claimNonce` with that key). Duplicate → 200, no second Gist write.

If `client_reference_id` or `metadata.user_id` is reserved (`craig` / `Jessica`, case-insensitive) **or** would `userStore.put` those ids: **200 no-op**, no Customer attach, no Gist write. Billing failures never SMS Jessica (D4).

`checkout.session.completed` + `sku=single_watch`: load `checkout:<session.id>`; write Gist rows with `recipient_phone` from the consumer’s current `user.phone` at apply time (same as planner POST); stamp the stored `billable_id` on every date row; set `stripe_customer_id` from `session.customer`; increment `single_watch_count`; delete pending blob. Claim `stripe_event:<id>` **only after** a successful apply (or reserved-id no-op). If Gist write throws: **do not** claim the event id, **do not** delete the pending blob, return **500** so Stripe retries. `/billing/sync` is the user-facing retry. If pending blob is missing, read `metadata.billable_id` from the Session. If Gist already has active date rows for that `owner_id` + `billable_id`, treat as success (idempotent 200). If blob and metadata are both missing, return **500** so Stripe retries.

`checkout.session.completed` + `sku=planner`: set `stripe_customer_id`, `planner_subscription_id`, `planner_status` from the Session/subscription (`active` / `trialing`). Do not write a watch from Planner checkout.

Subscription/invoice events update `planner_status`, `planner_subscription_id`, `planner_current_period_end`, `cancel_at_period_end` on the consumer record looked up by `stripe_customer_id`. If no row matches, fall back to `metadata.user_id` or Subscription/Checkout `client_reference_id` (must match a consumer id; reserved `craig`/`Jessica` → 200 no-op). Never attach by email alone. `deleted` → `canceled`. `invoice.payment_failed` on the Planner subscription → `past_due`.

Poller does not read Stripe. Entitlement for SMS is “row exists in Gist” plus existing STOP handling (unchanged).

### Server retrieve (D3)

`POST /_api/billing/sync` (session cookie required, consumer only): body `{ session_id }` optional. If `session_id` present, `stripe.checkout.sessions.retrieve` then apply the same mutation as `checkout.session.completed` (idempotent). If the user has `stripe_customer_id`, also retrieve the Planner subscription and refresh cache. Internal → 403. Browser `?paid=ok` **alone** must not flip entitlement; the frontend always calls `/billing/sync` then `/auth/me`.

### Planner Checkout and Portal (US-3.3, US-3.5)

`POST /_api/billing/checkout` body `{ sku: 'planner' }` → Session `mode=subscription`, `STRIPE_PRICE_PLANNER`, same bind rules. 403 for internal. 402 `past_due` should tell the user to use Portal, not a second subscription, if `stripe_customer_id` is set.

`POST /_api/billing/portal` → Stripe Billing Portal session if `stripe_customer_id` set; else **404** `{ code: 'no_customer' }`. Return URL `{origin}/?billing=portal`. Do not enable pause.

### Frontend (US-3.2, US-3.6, D7)

Logged-in consumer with `can_create_watch` true (planner **or** single_watch): enable `#create-btn` / `#bulk-btn`, show SMS consent (unchecked unless remembered), collect consent before POST, send `sms_consent: true`.

`billing_mode === 'blocked'`: keep Slice 2 lock (disable create, hide/disable consent, show banner). Copy by `code`:

- `past_due`: “Update billing to add watches. Existing watches keep alerting.”
- `canceling`: “Your Planner stays active until the period ends. You can’t add watches.”
- `planner_cap`: “You’re at this month’s watch limit.”
- `billing_unavailable`: “Paid watches are not available yet. You can browse restaurants now.”

`billing_mode === 'single_watch'`: show `#billing-next-banner` **and** keep Create Watch enabled. Copy: “Pay once for this watch. You’ll go to Stripe to pay, then we’ll start watching. Paying is not text consent — check the box first.” Button label **Pay and watch**. Do not print dollar amounts.

`billing_mode === 'planner'` or internal: hide paywall banner; button **Create Watch**.

`#planner-checkout-btn` visible for consumers not on live Planner (`active`/`trialing`). `#billing-portal-btn` visible iff `has_stripe_customer`. `#upgrade-prompt` visible iff `upgrade_prompt` (after 2 Single Watch purchases). Planner button copy: “Start a monthly Planner” — no price number.

Phone: `#consumer-phone` still saves via `PATCH /me`. Create Watch / calendar add if `!has_phone` → focus phone, do not POST.

`smsConsentKey()` must use `mtfSessionUser.id` (not `getUserId()` / `disneyUserId`) for cookie consumers so consent does not bleed across guests.

In `bootSession`, before `onLogin()`: if query has `paid=ok`, `POST /billing/sync` with `session_id` from query, then refresh `/auth/me`; strip `paid`/`session_id` via `replaceState`. If query has `billing=portal`, call `/billing/sync` without `session_id`, then refresh. Failure shows a non-blocking error; do not treat query params alone as entitlement (D3). `?paid=cancel`: message “Payment canceled. Your watch was not started.” Stay on My Watches after a successful paid sync.

All Create Watch surfaces (`#watch-form`, `calAddWatch`, `watchAllGrey`) share one `postWatch(body)` helper. POST bodies include `sms_consent: true`. Banner for `single_watch` is driven by `billing_mode` (class or JS), not only `html:not(.can-create-watch)`, so it stays visible while Create Watch is enabled.

### Privacy / Terms

Name Stripe as the payment processor. State that Checkout is **not** SMS consent. Do not put secret keys in HTML.

### Tests (every AC)

- `tests/test_entitlement.js` — planner ok, single_watch ok, past_due/canceling/cap blocked, internal unchanged, `kind=consumer` on `craig` still not internal.
- `tests/test_stripe_billing.js` — fake Stripe: bind fields, no Session for internal, no `customer`+`customer_email`, reserved id no-op, idempotent event id, unpaid payload not passed to watch writer, paid apply calls writer once, planner does not write watches.
- `tests/test_consumer_auth_api.js` — cookie consumer POST without planner → 402 `checkout_required` + `checkout_url`, **zero** Gist (spy `setWatchWriterForTests`); with `sms_consent` false → 422; no phone → 422; planner user + injected writer → **201** and writer called once; webhook public; internal POST still not 402 `checkout_required`; `/billing/checkout` and `/billing/portal` 403 for `craig`.
- `tests/test_landing_contract.py` — ids `#planner-checkout-btn`, `#billing-portal-btn`, `#upgrade-prompt`; copy “Pay once for this watch”; `checkout_url`; `sms_consent`; no `$` price in `index.html` for SKUs; `paid=ok`.
- Existing Slice 1–2 gates stay green (update Slice 2 assertions that required consumer `can_create_watch === false` and `billing_required`).

### Out of scope

Live Stripe keys in Cloud, sending a real Checkout, public launch (Slice 4), poller/Disney session, `netlify.toml`, pause in Portal, dollar amounts, changing cap default away from 8 unless env set, Brunch, Disneyland, auto-book, free SMS, Goose/Claude Code.

---

# Slice 1 — Dining selection (shipped)

Shipped on `main` (PR #11). Family app stayed on `WATCH_USERS` login. No Stripe. No new user store. Do not reopen Slice 1 in this PR except to keep existing landing/dining tests green.

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

# Slice 2 — Consumer identity (shipped)

Identity plumbing only. No Stripe Checkout, no Customer Portal, no webhooks, no consumer rows in `watches.json`. A consumer who signs in with email **must not** get a live SMS watch. Slice 4 still owns marketing launch and a global poller budget.

Auth is high-risk. Live `MAGIC_LINK_SECRET` / `RESEND_API_KEY` stay in Netlify env, never in the repo or Cloud Agent secrets. Tests inject a sender and an in-memory store. Cloud must not send a real magic-link email.

## Assumptions

- Email magic link is the public consumer login. Phone is not a login factor. Google OAuth is out. Slice 2 ships **identity** on the landing; it does not ship a live paid or free SMS watch (that is Slice 3). Slice 4 is marketing launch + poller budget, not “hide the email field.”
- `GET /_api/profiles` still returns Craig/Jessica so `scripts/smoke_test_api.py` keeps working. That is **not** a public directory: the landing must not render those names as a picker, chips, or list. Cloud does not run live smoke (no `API_SECRET`); `tests/test_consumer_auth_api.js` asserts `/profiles` includes `craig`.
- Magic-link callback is `GET /_api/auth/callback` because `netlify.toml` sends unmatched paths to the SPA. A bare `/auth/callback` would never hit the function.
- Same-origin `fetch('/_api/...')` carries cookies. Keep `Access-Control-Allow-Origin: *` for header-based internal/API clients. Do not require credentialed CORS for this slice.
- Until Slice 3, `can_create_watch` is true only for internal `WATCH_USERS` identities.

## Builder contract (do not invent)

All auth routes live in `netlify/functions/api.js` `exports.handler`, using helpers from `session_auth.js`, `user_store.js`, and `entitlement.js`. Do not add a second Netlify function or change `netlify.toml`.

**HMAC tokens (magic link and session cookie):** `base64url(JSON_payload) + "." + base64url(hmac_sha256(MAGIC_LINK_SECRET, payload_b64))`. Magic-link payload: `{ email, nonce, exp }` with `exp` = now + 900 seconds (unix). Session payload: `{ uid, exp }` with `exp` = now + 30 days. Verify with `crypto.timingSafeEqual`. Email normalization: `trim` + `toLowerCase` only (no Gmail-dot canonicalization).

**Public paths (skip password/`X-API-Secret`; handled before identity gate):** `GET /profiles`, `GET /health`, `POST /auth/magic-link`, `GET /auth/callback`, `GET /auth/me`, `POST /auth/logout`. Replace today’s `checkSecret()` gate: protected routes require `resolveIdentity(event)` to return a user. **A valid `mtf_session` is sufficient; consumers have no password and must not be asked for `X-API-Secret`.**

**`resolveIdentity` order:** (1) `X-User-Id` present **and** `X-API-Secret` equals that `WATCH_USERS` user’s password → `{ ...user, kind: 'internal' }`; (2) else valid `mtf_session` whose `uid` loads from the user store → consumer; (3) else `null` (401 on protected routes). Do **not** fall back to `DEFAULT_OWNER_ID` / `craig` when headers are empty. Empty `X-API-Secret` must not authenticate as internal even if `X-User-Id` is `craig`.

**`apiFetch`:** `credentials: 'include'`. Send `X-API-Secret` only when `getSecret()` is non-empty; send `X-User-Id` only when `getUserId()` is non-empty. `getUserId()` returns `localStorage disneyUserId` or `''` — never a hardcoded `craig`. Cookie-only calls therefore send neither auth header.

**Cookie-only API (must be tested):** after a valid session cookie and **no** `X-User-Id`/`X-API-Secret`, `GET /status` and `GET /watches` return 200 scoped to the consumer; `POST /watches` returns 402 with body `{ "detail": "<honest paid-watches-are-next sentence>", "code": "billing_required", "can_create_watch": false }` and must not call Gist write.

**Invalid magic link:** `GET /auth/callback` with bad/expired/reused token → **302** `Location: /?signin=invalid` and no `Set-Cookie` for `mtf_session`. Frontend: if `URLSearchParams` has `signin=invalid`, `showLogin({ scrollToSignin: true, message: "That sign-in link is invalid or expired. Request a new one." })` and `history.replaceState` to strip the query.

**`mtf_ui` stale:** if first paint set `has-session` from `mtf_ui=1` but `GET /auth/me` is 401 and there is no `disneyApiSecret`, remove `has-session`, `showLogin()`, and `POST /auth/logout` (clears both cookies).

**Internal header secret:** `X-API-Secret` must equal that user’s `WATCH_USERS` password when the password is non-empty; if the password is empty, accept `API_SECRET` (same fallback as today’s `checkSecret`). Do not treat `API_SECRET` as a bypass when a per-user password is set.

**`POST /_api/auth/magic-link` body:** JSON `{ "email": "<string>" }` only.

**`PATCH /_api/me` phone:** trimmed string, max 40 characters; no E.164 requirement this slice. Empty string clears phone.

**Create Watch when `can_create_watch` is false (one behavior, all surfaces):** show `#billing-next-banner`; disable `#create-btn` and `#bulk-btn`; do **not** POST from `#watch-form`, `calAddWatch`, `watchAllGrey`, or calendar day clicks; leave `#sms-consent` and `#modal-sms-consent` unchecked and do not require them (hide or disable both). **See dates** may still open the calendar for browsing. D7 stands: SMS consent is only collected when a watch can actually be created (Slice 3). If a consumer POST still reaches the API, return the 402 body above (defense in depth) — UI must not rely on that path.

**`PATCH /_api/me` phone** does **not** grant SMS consent, does not replace `#sms-consent`, and does not make `can_create_watch` true. Phone on the consumer record is a delivery address for Slice 3, not an opt-in.

**Magic link vs internal ids:** every magic-link email creates/loads a **consumer** (`kind: 'consumer'`, id `u_` + hex). `WATCH_USERS` has no email field; never authenticate a magic link as `craig`/`Jessica`. Store `put` rejects ids `craig` and `Jessica`.

**`privacy.html`:** state that email is used to send a sign-in link; signing in and saving a phone number are **not** SMS consent; SMS consent remains the unchecked Create Watch checkbox.

**Node test gate** (each file is its own process; do not pass multiple scripts to one `node` invocation):

```bash
node tests/test_user_lookup.js
node tests/test_entitlement.js
node tests/test_user_store.js
node tests/test_session_auth.js
node tests/test_consumer_auth_api.js
```

`tests/test_consumer_auth_api.js` must cover: public path bypass; cookie-only GET /status 200; cookie-only POST /watches 402 without Gist write; internal headers POST still allowed by entitlement (201 if Gist/local write works, or assert `canCreateWatch` ok plus handler returns non-402 before write — prefer invoke handler with no `GITHUB_GIST_ID` and a consumer cookie for 402, and invoke with internal headers expecting 401/5xx only after entitlement pass is proven via unit tests); `GET /profiles` includes `craig`. Tests set `MTF_USER_STORE=memory` and `MAGIC_LINK_SECRET` in-process. Inject magic-link sender. Never require `RESEND_API_KEY` in Cloud.

### User story US-2.1 — Magic link for consumers

As a new guest, I sign in with an email magic link and get a session cookie. I never see a Craig/Jessica profile directory. Phone is for SMS later, not login.

**AC**

1. Landing keeps existing IDs: `#login-overlay`, `#login-profile`, `#login-pwd`, `#login-btn`, `#login-error`. Do not add `id="login-form"`, `profile-select`, `password-input`, `signin-form`, `app.html`, or an `autofocus` attribute. Username/password submit still goes through `attemptLogin` + `GET /_api/status`.
2. New IDs (additive): `#login-email`, `#login-magic-btn` (`type="button"` so it does not submit the password form), `#login-magic-status`. Copy distinguishes **Email a sign-in link** from **Private sign-in**. Overlay must not contain a public list of Craig/Jessica accounts. Do not add the string `For Craig and Jessica`.
3. `POST /_api/auth/magic-link` is on the public-path list (see Builder contract). Always **200** `{ "ok": true }` (no email enumeration), including invalid email, unknown email, and missing Resend key. Valid emails mint a token per Builder contract. Link: `{site}/_api/auth/callback?token=...` (`site` from `URL` then `DEPLOY_PRIME_URL` then `https://magictablefinder.com`).
4. Email is sent via Resend HTTP API (`RESEND_API_KEY`, `MAGIC_LINK_FROM`). Tests inject a sender; they must not require a live key. Production must not log the raw token. If secret or Resend is missing, still return `{ok:true}` and do not send.
5. `GET /_api/auth/callback?token=` verifies signature, expiry, and single-use (nonce stored under user-store key `used:{nonce}`). On success: upsert consumer, `Set-Cookie` `mtf_session` (httpOnly, `Path=/`, `SameSite=Lax`, `Secure` iff request is HTTPS, Max-Age 30 days) and `mtf_ui=1` (not httpOnly, same Path/SameSite/Secure/Max-Age). Redirect **302** to `/?signin=ok` (US-2.5). Invalid/expired/reused: **302** `/?signin=invalid` and do not set `mtf_session` (see Builder contract).
6. `GET /_api/auth/me` is public-path: no `X-API-Secret` required. Returns 200 `{ user: { id, email, name, kind, has_phone, can_create_watch } }` for `resolveIdentity`; otherwise 401. Consumer `email` is the stored email; internal `email` may be `""`. `POST /_api/auth/logout` clears both cookies (Max-Age=0) and returns 204.
7. Frontend follows Builder contract (`credentials`, omit empty auth headers, `getUserId` default gone). **Boot order is US-2.5 / hotfix Builder contract §2 — this AC7 password-first sentence is superseded.** Cookie `GET /_api/auth/me` first; private `disneyApiSecret` only after `/auth/me` 401, and only after a raw `/status` probe succeeds. 401 with `mtf_ui` and no working secret → stale-cookie path. Logout: clear localStorage **and** `POST /_api/auth/logout`. Inline first-paint: `disneyApiSecret` **or** `mtf_ui=1` → `html.has-session`. `refreshStatus` must run for cookie **or** secret (`onLogin`).
8. Phone is not a login field. Optional `PATCH /_api/me` `{ "phone": "..." }` on a **consumer** session only (internal → 403) stores `phone` on the consumer record (not Gist, not `WATCH_USERS`). This is **not** SMS consent (Builder contract + `privacy.html`). Must not gate login. Signed-in consumer UI may include `#consumer-phone` (optional).

**Files:** `netlify/functions/session_auth.js`, `netlify/functions/api.js`, `public/index.html`, `public/privacy.html` (email used for sign-in), tests listed in US-2.4.

### User story US-2.2 — Internal owners stay unrestricted

As Craig or Jessica, I still use the private name+password path. Create Watch never sends me to Stripe. I have no watch cap.

**AC**

1. `attemptLogin` + `X-User-Id` + `X-API-Secret` against `WATCH_USERS` still returns 200 from `GET /_api/status` and 201 from `POST /_api/watches` for `craig` and `Jessica`. No Checkout redirect, no 402, no cap.
2. `netlify/functions/entitlement.js` exports `isInternalUser(user)` and `canCreateWatch(user)`. Internal = `kind === 'internal'` or id present in parsed `WATCH_USERS` (including `craig` / `Jessica`). Consumers are never internal.
3. `canCreateWatch` is `{ ok: true, code: 'internal' }` for internal users. For consumers: `{ ok: false, code: 'billing_required', status: 402, detail: 'Paid watches are next. You can browse restaurants now.' }`.
4. `POST /_api/watches` calls `canCreateWatch` **before** `loadWatches` / `saveWatches`. Consumer (cookie-only or otherwise) → **402** `{ detail, code: 'billing_required', can_create_watch: false }` and **zero** Gist writes. Internal → existing validation + 201.
5. `resolveIdentity` as in Builder contract. A consumer cookie must never be rewritten to `craig`. Empty headers plus a consumer cookie is the consumer, not `DEFAULT_OWNER_ID`.
6. `GET /_api/watches` and `GET /_api/status` for a consumer are owner-scoped to that consumer id (empty list is fine). They must not return Craig/Jessica watches.
7. Webhooks (not built this slice) must never attach a Stripe Customer to `craig` or `Jessica`. Entitlement helper is the shared place later poller/API will call. Do not edit `disney_bot.py` in this slice.
8. Billing failures never SMS Jessica (no Twilio/Signal calls in this slice).

**Files:** `netlify/functions/entitlement.js`, `netlify/functions/api.js`, tests in US-2.4.

### User story US-2.3 — Users do not live in Gist or `WATCH_USERS`

As an operator, consumer accounts and entitlement live in a real store. Gist stays poller health / `open_slots` / `seen_slots` / `watches.json` / calendars until a later cutover. Do not clear those files.

**AC**

1. New `netlify/functions/user_store.js`: get/put by id and by normalized email (`trim` + `toLowerCase`). Production backend is Netlify Blobs store name `mtf-users`. Tests use an in-memory backend (`MTF_USER_STORE=memory` or injected map). Never read or write consumer records via Gist. Never append consumers to `WATCH_USERS`.
2. Consumer record shape (fields may be null until Slice 3): `id`, `email`, `phone`, `created_at`, `kind: 'consumer'`, `stripe_customer_id`, `planner_status` (`none` until Slice 3), `planner_subscription_id`, `planner_current_period_end`, `cancel_at_period_end`.
3. New consumer ids are `u_` + hex (or equivalent). **Never** mint `craig` or `Jessica`. Upsert by email reuses the same id. Internal users stay only in `WATCH_USERS`; the store must refuse to save those ids.
4. Used magic-link nonces live in the user store (or equivalent), not in Gist.
5. `PRODUCT.md` Consumer direction: Slice 2 is current; consumer identities live in Netlify Blobs (`mtf-users`); Gist file list is unchanged; do not clear `open_slots.json` / `seen_slots.json`. Document env names only (`MAGIC_LINK_SECRET`, `RESEND_API_KEY`, `MAGIC_LINK_FROM`) — no values.
6. Tests set `MTF_USER_STORE=memory` before requiring the store. Production must not silently fall back to memory if `@netlify/blobs` `getStore('mtf-users')` throws — that mints a session for a user the next Lambda cannot load. Do not fall back to Gist.

**Files:** `netlify/functions/user_store.js`, `PRODUCT.md`, tests in US-2.4.

### User story US-2.4 — Honest consumer app + gates

As a consumer who magic-linked in, I can see the app but I cannot create a live watch yet. Copy is honest.

**AC**

1. When `can_create_watch` is false: show `#billing-next-banner` (“Paid watches are next. You can browse restaurants now.”); disable `#create-btn` and `#bulk-btn`; do not POST from the create form, `calAddWatch`, `watchAllGrey`, or calendar day clicks; do not require `#sms-consent` or `#modal-sms-consent` (see Builder contract). See dates still opens the calendar. Do not fake a 201. If POST happens anyway, API 402 `detail` may show on `#create-msg.err` or `#modal-msg`.
2. Empty My Watches copy may stay `No watches yet. Create one above.` Internal users unchanged.
3. Quiet Luxury landing tokens and locked headlines in `tests/test_landing_contract.py` stay green. Add assertions for `#login-email`, `#login-magic-btn`, and `?signin=invalid` handling. Do not steal focus on first paint (`autofocus` still forbidden). Sign-in nav may still focus `#login-pwd` after click, as today.
4. Gates: `python3 -m unittest tests.test_alert_semantics tests.test_landing_contract tests.test_dining_selection_contract`; then the five separate `node tests/test_*.js` commands in the Builder contract; extract last `<script>` from `public/index.html` → `node --check`.
5. Do not edit `disney_bot.py`, `monitor.py`, `notify.py`, `seed_disney_session.py`, `open_slots.json`, `seen_slots.json`, `.env`, or Stripe. Do not `playwright install`. Do not add Cloud secrets. Live `scripts/smoke_test_api.py` is not a Cloud gate; keep `/profiles` + internal password auth compatible so it still works in production.

**Files:** `public/index.html`, `tests/test_landing_contract.py` (additive), new Node tests above.

---

# Slice 2 hotfix — Magic-link click must sign in (build now)

Production (2026-08-30): Resend delivers the mail. Clicking the link shows the landing overlay and red **Please sign in** (`GET /_api/status` 401 `detail`). The account is created only on callback consume, not on send. Stay off `main` until Craig says deploy.

## Assumptions

- Craig’s browser may still have `disneyApiSecret` / `disneyUserId` from private sign-in. That leftover must not steal or race a magic-link click.
- Netlify `200` rewrite of `/_api/*` plus a **302 with two `Set-Cookie` values only in `multiValueHeaders`** can drop cookies. The httpOnly session cookie must survive even if `mtf_ui` does not.
- Plain-text URLs wrap in mail clients (~76 chars). The token URL is longer; HTML `<a href>` is required in addition to `text`.
- Do not change `netlify.toml`, Stripe, poller, or Disney session.

## Builder contract (hotfix)

1. **No status fetch before boot.** `public/index.html` must not call `refreshStatus();` at script top-level. `refreshStatus` runs from `onLogin` / interval only. Landing contract: the file must not contain a newline immediately followed by `refreshStatus();` (indented calls inside functions are fine).
2. **`bootSession` order (supersedes US-2.1 AC7 password-first boot):** (a) `?signin=invalid` → existing invalid copy + `replaceState`, **return**. (b) `GET /_api/auth/me` with `credentials: 'include'` and **no** `X-User-Id` / `X-API-Secret`. 200 → set `mtfSessionUser`; if `kind === 'consumer'`, `localStorage.removeItem` both `disneyApiSecret` and `disneyUserId`; write `mtf_ui=1` from JS (`Path=/`, `SameSite=Lax`, `Max-Age` 30 days, `Secure` on https); `hideLogin()` + `onLogin()`; if `signin=ok` strip query. (c) if `signin=ok` and `/auth/me` not 200 → `showLogin({ scrollToSignin: true, message: "That sign-in link didn't complete. Request a new one." })`, strip query, **do not** fall back to `disneyApiSecret` (cookie was dropped; leftover private login must not paint API `Please sign in`). (d) else private fallback only via **raw** `fetch('/_api/status')` with stored headers (not `apiFetch`): 200 → `hideLogin()` + `onLogin()`; 401 → clear both localStorage keys and `showLogin()` with **empty** `#login-error` (never copy `data.detail`). (e) else stale `has-session` → logout + `showLogin()`.
3. **`apiFetch`:** if `mtfSessionUser && mtfSessionUser.kind === 'consumer'`, do **not** send `X-User-Id` or `X-API-Secret` even if localStorage still has them.
4. **`redirect(location, cookies)`:** always put the full cookie list on `multiValueHeaders['Set-Cookie']`. Also set `headers['Set-Cookie']` to the **session** cookie string (`mtf_session`, first entry) so a Netlify rewrite that keeps a single `Set-Cookie` still stores the session. Keep `Location` / `Cache-Control` only on `headers`. Success Location is `/?signin=ok`. Invalid remains `/?signin=invalid` with **no** session cookie.
5. **Resend:** `magicLinkEmailPayload(url)` returns `{ subject, text, html }`. `html` includes `<a href="{escaped url}">Sign in to Magic Table Finder</a>` plus the expiry sentence. `text` still includes the raw URL. `sendViaResend` JSON includes `html`. Tests cover the helper; they must not send live mail.
6. **Callback token:** `queryStringParameters.token` or, if empty, parse `event.rawQuery` / `event.rawQueryString` via `URLSearchParams`.
7. **`user_store.getBackend`:** `MTF_USER_STORE=memory` → memory. Otherwise `blobBackend()` and let `getStore` throw (handler 500). No silent memory fallback.

## User story US-2.5 — Clicking the email link signs me in

As a guest who received the magic-link email, I click it once and land in the app (Create Watch still blocked until Slice 3). I do not see red **Please sign in** from a leftover private session.

**AC**

1. `public/index.html` has no top-level `refreshStatus();` (landing contract: no newline immediately followed by `refreshStatus();` — indented calls inside functions are allowed). Interval + `onLogin` still refresh.
2. Cookie `/auth/me` 200 as consumer clears leftover private localStorage; `apiFetch` omits `X-User-Id`/`X-API-Secret` while `mtfSessionUser.kind === 'consumer'` (landing contract asserts that guard string).
3. Callback tests: 302 `/?signin=ok` with `multiValueHeaders['Set-Cookie']` containing `mtf_session` and `mtf_ui`, **and** `headers['Set-Cookie']` (string) containing `mtf_session`. Empty `queryStringParameters` plus `rawQuery: 'token='+token` still 302 `/?signin=ok`.
4. `magicLinkEmailPayload(url)` html contains `href="` + the callback URL; text still contains the URL. `sendViaResend` JSON includes `html`.
5. `getBackend()` without `MTF_USER_STORE=memory`: stub `blobBackend` / `getStore` to throw → `getBackend()` throws; it must not return `kind: 'memory'`.
6. Landing copy: `signin=ok` handling string `That sign-in link didn't complete` exists in `index.html`. Invalid/reused token still 302 `/?signin=invalid` with no `mtf_session`.
7. US-2.1 AC7 is superseded by this boot order (stated in AC7 itself). Existing Slice 2 gates stay green.

**Files:** `public/index.html`, `netlify/functions/api.js`, `netlify/functions/session_auth.js`, `netlify/functions/user_store.js`, `CONSUMER-EPIC.md`, `tests/test_landing_contract.py`, `tests/test_consumer_auth_api.js`, `tests/test_session_auth.js`, `tests/test_user_store.js`.

**Out of scope:** Stripe, `netlify.toml`, VPS, Disney session, changing HMAC format, logging raw tokens.

---

# Slice 2 hotfix — Netlify Blobs Lambda connect (build now)

Production (2026-08-30, after US-2.5): click stays on `/_api/auth/callback?token=…` and Chrome shows JSON `{"detail":"The environment has not been configured to use Netlify Blobs. To use it manually, supply the following properties when creating a store: siteID, token"}`. Classic `exports.handler` is Lambda-compat; `@netlify/blobs` requires `connectLambda(event)` when `event.blobs` is present, **before** `getStore`. Proven pattern: git `aaaf6d3` `attachBlobsFromEvent`. Do **not** put a Blobs PAT in git or Cloud secrets. Do **not** restore silent memory fallback.

## Builder contract

1. `user_store.connectBlobsFromEvent(event)`: no-op if `MTF_USER_STORE=memory` or `!(event && event.blobs)`. Else `connectLambda(event)` (injectable blobs module in tests). Guard `event.blobs` so test events without it do not throw.
2. Call it in `exports.handler` **after** the OPTIONS return and **before** any `userStore` / `handleAuthCallback` / `resolveIdentity`. All blob routes share this (callback, `/auth/me`, `/status`, `PATCH /me`), not callback-only.
3. `blobBackend()` calls `connectBlobsFromEvent` then `getStore({ name: 'mtf-users' })` (default consistency — not `strong`, which needs `uncachedEdgeURL` Lambda does not provide). Still no silent memory fallback.
4. `GET /auth/callback`: if consume/store throws, **302** `/?signin=error` with no `mtf_session`. Never return the Blobs `siteID, token` JSON to a browser on that path.
5. Frontend `?signin=error` → `showLogin({ scrollToSignin: true, message: "Sign-in is temporarily unavailable. Request a new link in a minute." })` + `replaceState`.

## User story US-2.6 — Callback uses Blobs in Lambda mode

As a guest who clicks the email link, the function can use `mtf-users` and I land signed in (or a human message), never JSON config.

**AC**

1. `connectBlobsFromEvent({ blobs: { token: 't' } })` with stub `connectLambda` is called when `MTF_USER_STORE` is unset; with `MTF_USER_STORE=memory` it is not. Without `event.blobs`, `connectLambda` is not called.
2. `api.js` handler calls `connectBlobsFromEvent(event)` (test: source includes that call, or spy).
3. If `consumeMagicToken` throws, `GET /_api/auth/callback` → **302** `/?signin=error`, no `mtf_session` cookie.
4. Landing: `signin=error` and `Sign-in is temporarily unavailable` in `public/index.html`.
5. Existing Slice 2 / US-2.5 gates stay green. No `netlify.toml` change. No new env vars.

**Files:** `netlify/functions/user_store.js`, `netlify/functions/api.js`, `public/index.html`, `CONSUMER-EPIC.md`, `tests/test_user_store.js`, `tests/test_consumer_auth_api.js`, `tests/test_landing_contract.py`.

**Out of scope:** Stripe, VPS, Disney session, Functions API v2 rewrite, adding `siteID`/`token` secrets.

---

### User story US-3.1 — Bind Checkout to the logged-in user

As a paying guest, Checkout is created for **my** account after I am signed in, not for a guest email typed into Stripe.

**AC**

1. Fake Stripe `checkout.sessions.create` args include `client_reference_id` equal to the consumer `user_id`, `metadata.user_id` the same, `metadata.sku` `single_watch` or `planner`.
2. When `user.stripe_customer_id` is set, args include `customer` and **omit** `customer_email`.
3. When it is not set, args include `customer_email` equal to the session email and **omit** `customer`.
4. Internal identity never receives a Session (403 `internal_no_stripe`). Webhook with `user_id` `craig` or `Jessica` is 200 no-op.

**Files:** `netlify/functions/stripe_billing.js`, `netlify/functions/api.js`, `tests/test_stripe_billing.js`, `tests/test_consumer_auth_api.js`.

### User story US-3.2 — Single Watch purchase

As a consumer without live Planner, I create a watch, agree to SMS, pay once, then that billable watch goes live.

**AC**

1. Cookie consumer, `sms_consent: true`, phone on file, planner none → POST `/watches` **402** `checkout_required` with `checkout_url` starting `https://`; watch writer **not** called.
2. Same request with `sms_consent` false/missing → 422, no Checkout.
3. No phone → 422 `phone_required`, no Checkout.
4. Fake `checkout.session.completed` (or `/billing/sync`) writes one `billable_id` across all dates in the pending payload; writer called once; quantity on the Price is 1 regardless of date count.
5. Frontend: `Pay and watch`, `checkout_url`, `sms_consent` in the POST body, `postWatch` used by form + calendar + bulk (not generic `apiFetch` for that POST). `smsConsentKey()` uses `mtfSessionUser.id` for consumers.
6. In `bootSession`, `?paid=ok` calls `POST /billing/sync` with `session_id` before `onLogin()`; query is not entitlement.

**Files:** `netlify/functions/api.js`, `netlify/functions/stripe_billing.js`, `public/index.html`, `tests/test_consumer_auth_api.js`, `tests/test_stripe_billing.js`, `tests/test_landing_contract.py`.

### User story US-3.3 — Planner subscription

As a consumer who keeps adding restaurants, I subscribe once and create watches in-app under the cap.

**AC**

1. POST `/billing/checkout` `{ sku: 'planner' }` → fake Session `mode=subscription` with `STRIPE_PRICE_PLANNER`.
2. User with `planner_status` `active` or `trialing`, under cap, `cancel_at_period_end` false → POST `/watches` with consent + phone **201** path (writer called, no Checkout).
3. At cap → 402 `planner_cap`, no write. Before returning `planner_cap`, handler must load Gist and pass `activeBillableCount` (test: cap asserted only when count ≥ `PLANNER_WATCH_CAP`).

**Files:** `netlify/functions/entitlement.js`, `netlify/functions/stripe_billing.js`, `netlify/functions/api.js`, `public/index.html`, tests above.

### User story US-3.4 — Entitlement cache and webhooks

As the site, Stripe events (not the browser query string) decide whether a consumer is on Planner.

**AC**

1. Consumer record fields: `stripe_customer_id`, `planner_status`, `planner_subscription_id`, `planner_current_period_end`, `cancel_at_period_end`, `single_watch_count`.
2. Webhook verifies signature on raw body; bad sig → 400.
3. Duplicate `event.id` → 200, writer not called twice.
4. `past_due` / `canceling` → `can_create_watch` false; tests do not require deleting Gist rows.
5. `/auth/me` `can_create_watch` is true for `billing_mode` `single_watch` (Checkout path) and `planner` / `internal`. It is false for `blocked`. `?paid=ok` without `/billing/sync` does not set `planner_status` or write Gist.

**Files:** `netlify/functions/entitlement.js`, `netlify/functions/stripe_billing.js`, `netlify/functions/api.js`, `netlify/functions/user_store.js` (emptyRecord fields + checkout blob helpers if needed), tests.

### User story US-3.5 — Customer Portal

As a consumer who already has a Stripe Customer, I manage card and cancel at period end.

**AC**

1. POST `/billing/portal` with `stripe_customer_id` → `{ url }` from fake portal sessions.
2. Without customer → 404 `no_customer`.
3. Internal → 403.
4. `#billing-portal-btn` in HTML, shown when `has_stripe_customer`. No pause language.

**Files:** `netlify/functions/stripe_billing.js`, `netlify/functions/api.js`, `public/index.html`, tests.

### User story US-3.6 — Upgrade prompt

As a guest on my second Single Watch, I see an offer to start Planner (no dollar figure).

**AC**

1. `single_watch_count >= 2` and not live Planner → `upgrade_prompt` true and `#upgrade-prompt` visible.
2. Copy must not include `$` or a numeric monthly price.
3. CTA uses `#planner-checkout-btn` / POST `/billing/checkout`.

**Files:** `netlify/functions/entitlement.js`, `public/index.html`, `tests/test_entitlement.js`, `tests/test_landing_contract.py`.

### User story US-3.7 — Cancel vs STOP

Cancel at period end blocks **new** watches; existing paid dates keep alerting. STOP remains poller/Twilio behavior (do not edit `notify.py`).

**AC**

1. `cancel_at_period_end` true with `planner_status` active → `canCreateWatch` `canceling`, 402, no Gist write.
2. Privacy/Terms: Stripe processor + Checkout is not SMS consent; STOP still opts out.
3. No poller file changes.

**Files:** `netlify/functions/entitlement.js`, `public/privacy.html`, `public/terms.html`, tests.

# Slice 3 files that will change

- `CONSUMER-EPIC.md` (this file)
- `PRODUCT.md`
- `public/index.html`
- `public/privacy.html`
- `public/terms.html`
- `netlify/functions/api.js`
- `netlify/functions/entitlement.js`
- `netlify/functions/user_store.js`
- `netlify/functions/stripe_billing.js` (new)
- `netlify/functions/package.json` (add `stripe`)
- `tests/test_entitlement.js`
- `tests/test_stripe_billing.js` (new)
- `tests/test_consumer_auth_api.js`
- `tests/test_landing_contract.py` (additive IDs / copy)
- `tests/test_user_store.js` only if checkout blob helpers land here

Do not change: `disney_bot.py`, `watch_store.py`, `notify.py`, `netlify.toml`, Gist files, `.env`, `DISNEY_HEADLESS`, recovery cooldown. Do not add Cloud secrets for Stripe.

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

# Slice 2 files that will change

- `CONSUMER-EPIC.md` (this file)
- `PRODUCT.md`
- `public/index.html`
- `public/privacy.html` (email for sign-in only; no Stripe processor language)
- `netlify/functions/api.js`
- `netlify/functions/entitlement.js` (new)
- `netlify/functions/user_store.js` (new)
- `netlify/functions/session_auth.js` (new)
- `netlify/functions/package.json` only if `@netlify/blobs` is required to load the production backend
- `tests/test_entitlement.js` (new)
- `tests/test_user_store.js` (new)
- `tests/test_session_auth.js` (new)
- `tests/test_consumer_auth_api.js` (new)
- `tests/test_landing_contract.py` (additive IDs only)

Do not change: `disney_bot.py`, `watch_store.py`, `notify.py`, `netlify.toml` (unless a reviewer proves `/_api/*` no longer reaches `api.js`), Gist files, `.env`.
