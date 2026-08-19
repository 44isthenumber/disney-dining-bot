# Slice 1 — Real user identity

Status: draft for `/deliver`. Builder: Grok. Spec-verify / QA / validator must be different models.

## Why

Live “login” is a public profile picker (`GET /_api/profiles`) plus `X-User-Id` + `X-API-Secret` checked against `WATCH_USERS` JSON in env (`watch_store.py:_parse_users`, `netlify/functions/api.js` `parseUsers` / `checkSecret` / `currentUser`). `auth.py` is Disney JWT helpers, not people.

The 2026-08-18 public-open eval showed the poller can share Disney requests (`grouped_restaurant_requests`). Product still cannot go public on a `WATCH_USERS` allowlist, a Gist last-write-wins user file, or a world-readable picker.

This slice is **people identity only**. Not the poller. Not Disney. Not SMS send. Not moving watches off Gist.

## User story

A person can create a Magic Table Finder account (email, password, phone, SMS consent) and log in. The server knows who they are from an httpOnly session cookie. Craig and Jessica keep their existing `owner_id` strings (`craig`, `Jessica`) and existing Gist watches. New signups get a new `user_*` id; watches they create are tagged with that id on the existing Gist `watches.json` path.

## Store choice (investigated)

| Option | Already in repo? | Cloud-safe? | Notes |
|---|---|---|---|
| `WATCH_USERS` env | Yes | N/A | Current allowlist. Cannot accept public signup. |
| GitHub Gist file | Yes (watches/state) | No write from Cloud tests | Last-write-wins. Explicitly rejected for users. |
| Netlify Blobs | Platform already used (Netlify Functions) | Yes | No new vendor, no spend. **Pick.** |
| Stripe / Neon / Supabase / D1 | Not in repo | Would add vendor | Out of scope. |

**Decision:** Netlify Blobs store `mtf-users`, one blob per user (`user:{id}`) plus `email:{normalized}` uniqueness keys. Classic Netlify Functions (`exports.handler`) must call `connectLambda(event)` before `getStore` — do not pass Lambda `context` into `getStore`. This package’s `setJSON` does not support `onlyIfNew`; uniqueness is write-then-read confirmation, then delete the user blob if the email pointer is no longer ours. Tests inject an in-memory adapter. Do not silently fall back to memory in production (users would vanish between Lambdas).

The VPS worker keeps reading `WATCH_USERS` for `recipient_for()` fallback and admin operational alerts. Reservation alerts already use `slot.recipient_phone` stamped on each watch at create time (`api.js` `handlePostWatch`, `notify.py` `send_sms`). New users’ phones go on the watch record. Do not change `disney_bot.py` / Playwright / Gist watch I/O in this PR.

## Session

- Cookie name: `mtf_session`
- Value: HMAC-SHA256 signed payload `{uid, exp}` (base64url). Not JWT-from-a-library; Node `crypto` only.
- Flags: `HttpOnly`, `SameSite=Lax`, `Path=/`. `Secure` when the request is HTTPS (`x-forwarded-proto` or Netlify production).
- TTL: 30 days.
- Signing key: `SESSION_SECRET`. If unset, derive from `API_SECRET` so an existing Netlify deploy does not lock Craig/Jessica out before the new env var is added. Document `SESSION_SECRET` in `PRODUCT.md`.
- Frontend: `fetch(..., { credentials: "include" })`. Stop sending `X-API-Secret` / `X-User-Id` and stop storing the password in `localStorage` (`disneyApiSecret`).
- Logout clears the cookie.

## Auth API

Public (no session):

| Method | Path | Body | Result |
|---|---|---|---|
| `POST` | `/signup` | `{email, password, phone, name?, sms_consent}` | `201` + session cookie. New `user_{hex}` id. |
| `POST` | `/login` | `{identifier, password}` | `200` + session cookie. Identifier is email **or** legacy id (`craig` / `Jessica`). |
| `POST` | `/logout` | — | `204`, cookie cleared. |
| `GET` | `/health` | — | Unchanged (freshness boolean only). |

Session required (cookie):

| Method | Path | Result |
|---|---|---|
| `GET` | `/me` | `{id, name, email, has_phone}` — never `phone`, never password. |
| `GET` | `/status` `/restaurants` `/calendar/:id` `/watches` | Same payloads, `user` from session. |
| `POST` | `/watches` | `owner_id` + `recipient_phone` from session user. Gist write unchanged. |
| `DELETE` | `/watches/:id` | Owner-scoped, unchanged. |

**`GET /profiles` is not a public directory.** Return `404`. Login is email/password (or legacy id during migrate), not a picker of every user.

## Signup rules

- Email required, trimmed, lowercased, basic `local@domain` check. Unique.
- Password min 8 characters. Stored as scrypt (`crypto.scrypt`) with random salt. Never plaintext. Never logged.
- Phone required (channel-prefixed string as today). Stored on the user record for stamping onto watches. Never returned by `/me` or `/status`. Never logged.
- `sms_consent` must be `true`. Store `sms_consent_at`. Watch-create consent checkbox stays (A2P).
- Name optional; default to email local-part.
- New `id` is `user_` + 16 hex chars. Do **not** reuse `craig` / `Jessica` for new signups.

## Login / migrate rules

On first handler use, idempotently seed any `WATCH_USERS` / `DISNEY_USERS` entries that are not already in the blob store:

- Keep `id` exactly (`craig`, `Jessica`). **Do not rename `owner_id` on existing watches.**
- Hash the env password once; do not store env plaintext in Blobs.
- Copy `name` and `phone`.
- Email empty for seeded users. They log in with identifier `craig` or `Jessica` + their existing password.
- First-write-wins. Do not overwrite an existing blob user from env on later requests.
- Never write an `email:` index key for a blank email (Craig/Jessica).
- Also seed `FALLBACK_USERS` only when those entries include a password; empty-password fallback profiles are not accounts.

Login lookup: email index (case-insensitive) **or** user id (case-insensitive match, stored id preserved). `jessica` logs in as stored `Jessica`. Same generic failure for unknown user / bad password: `401` `{detail: "Incorrect email or password"}`.

`X-User-Id` and `X-API-Secret` are **not** authentication. Ignore them. Missing or invalid cookie on a protected route is `401`. Do not fall back to `DEFAULT_OWNER_ID` / `craig`.

## Frontend

Replace the public profile `<select>` with:

- Sign in: identifier + password.
- Create account: email, password, phone, SMS consent checkbox (unchecked by default).
- Copy: alerts go to the phone on the account; Craig/Jessica can sign in with their existing profile name.
- `Lock` / logout calls `POST /logout` and shows the overlay.
- Header still shows `profile.name` from `/status` or `/me`.
- Do not call `GET /profiles`. Clear `disneyApiSecret` / `disneyUserId` from `localStorage` on login and logout. SMS consent memory keys off the session user id from `/me`.
- Mobile-first; no new JS framework.
- Same-origin only. Do not add credentialed CORS. Current `Access-Control-Allow-Origin: *` stays harmless because the SPA is same-origin via `netlify.toml` `/_api/*`.

## Out of scope (hard)

- Disney session, VPS SSH, poller, `DISNEY_HEADLESS`, recovery cooldown, navigate-per-restaurant, refresh-failure handling.
- Sending Signal/Twilio. Adding Cloud secrets for Disney / Twilio / Signal / Gist write.
- Clearing `open_slots.json` / `seen_slots.json`.
- Moving watches off Gist (slice 2). Ripping `WATCH_USERS` from the VPS worker.
- Booking reservations. Scaling browsers.
- Password reset, email verify, OAuth, Stripe, Neon, Supabase, D1.
- Merge to `main` / production deploy.

## Files that will change

- `docs/specs/slice-1-user-identity.md` — this spec.
- `netlify/functions/lib/password.js` — hash / verify.
- `netlify/functions/lib/session.js` — sign / verify / cookie.
- `netlify/functions/lib/user-store.js` — Blobs + memory adapter, seed.
- `netlify/functions/lib/identity.js` — signup / login / resolve session user.
- `netlify/functions/api.js` — wire routes; replace `checkSecret` / `currentUser`.
- `netlify/functions/package.json` — `@netlify/blobs`.
- `public/index.html` — login/signup UI; cookie `fetch`.
- `tests/test_identity.js` — signup, login, session, owner scope, craig/Jessica migrate.
- `scripts/smoke_test_api.py` — login + cookie jar instead of public `/profiles`.
- `PRODUCT.md` — identity store, session cookie, `SESSION_SECRET`.

Unchanged on purpose: `disney_bot.py`, `monitor.py`, `auth.py`, `watch_store.py` poller path, Gist watch read/write shape, `open_slots.json` / `seen_slots.json`.

## Acceptance criteria (testable)

1. `POST /signup` with valid email, password (≥8), phone, `sms_consent: true` creates a `user_*` id, sets `mtf_session` httpOnly cookie, and does not return or log the password or phone.
2. `POST /signup` without consent, with short password, bad email, or duplicate email fails (`400`/`409`); no session cookie.
3. `POST /login` with that email + password returns `200` and a session cookie. Wrong password or unknown identifier returns `401` with the generic detail string.
4. Seeded `WATCH_USERS` `{craig, Jessica}` can `POST /login` with those ids and env passwords. Their stored `id` remains `craig` / `Jessica`.
5. `GET /status`, `GET /watches`, `POST /watches` without a valid cookie return `401`. With cookie, watches are filtered and created with `owner_id === session user.id`. Craig cannot see Jessica’s watches and vice versa.
6. A watch created by a new signup has `owner_id` equal to that `user_*` id and `recipient_phone` equal to the signup phone (server-side; not exposed in `publicWatch`).
7. `GET /profiles` returns `404` and does not list users.
8. Passwords in the store are scrypt hashes, never plaintext. Session cookie is `HttpOnly`.
9. `python3 -m unittest tests.test_alert_semantics` still passes (poller / alert semantics untouched).
10. Extracted `public/index.html` script passes `node --check`. `node --check netlify/functions/api.js` and `node --test tests/test_identity.js` pass.
11. Gist `watches.json` read/write path in `api.js` is still used. No VPS / Playwright / Disney files change.
12. Protected routes reject `X-User-Id` + `X-API-Secret` without a valid cookie (`401`). No silent fallback to `craig`.
13. `POST /login` `{identifier:"jessica", ...}` yields session `id === "Jessica"` and existing `Jessica` watches.
14. `POST /watches` ignores body `owner_id` and `recipient_phone`. Empty account phone → `422`, not an empty stamp.
15. `normalizeWatch` / `saveWatches` never overwrite a present `recipient_phone` from `WATCH_USERS` lookup.
16. Production store (`MTF_USER_STORE` unset) uses Blobs and fails closed — no silent memory fallback.

## Test plan

- Node: in-memory user store + `createHandler({ store, secret, now })` covering AC 1–8, 11 (API contract).
- Python: existing `tests.test_alert_semantics` (AC 9).
- Frontend: extract `<script>` from `public/index.html` → `node --check` (AC 10).
- Do not run `disney_bot.py`, Playwright, or live production smoke from Cloud. Do not send SMS.
