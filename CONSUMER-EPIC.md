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

**Slice 2 is the only slice to build now.** Stories US-2.1 through US-2.4. Slice 1 is shipped on `main`. Slices 3–4 are backlog; citing Stripe Checkout, Customer Portal, or Gist watch cutover in this PR is drift.

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

# Slice 2 — Consumer identity (build now)

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
3. `blobBackend()` calls `connectBlobsFromEvent` then `getStore({ name: 'mtf-users', consistency: 'strong' })`. Still no silent memory fallback.
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

# Slice 3 — Stripe hybrid (backlog)

Do not implement in the Slice 2 PR. Prices are placeholders.

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
