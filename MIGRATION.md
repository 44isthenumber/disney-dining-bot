# Netlify → Cloudflare Pages migration

Magic Table Finder moves static assets from `public/` and the `/_api/*` backend from Netlify Functions to **Cloudflare Pages + Pages Functions**, with **Cloudflare KV** replacing Netlify Blobs for consumer identity (`mtf-users`).

**Do not merge this PR until Craig completes the cutover checklist below.** This PR does not change DNS, delete Netlify, or run blob export/import.

## Architecture after cutover

| Layer | Before | After |
| --- | --- | --- |
| Static site | Netlify `public/` | Cloudflare Pages `public/` (`_redirects`, `_headers`) |
| API | `netlify/functions/api.js` @ `/_api/*` | `functions/_api/[[path]].js` @ `/_api/*` |
| Consumer users | Netlify Blobs `mtf-users` | KV binding `MTF_USERS` |
| Watches / bot state | GitHub Gist (unchanged) | GitHub Gist (unchanged) |
| Disney poller | VPS systemd (unchanged) | VPS systemd (unchanged) |

Shared API logic lives in `functions/lib/`. `netlify/functions/*.js` are thin re-exports so existing Node tests keep working until Netlify is retired.

## VPS / poller note

The production poller (`disney_bot.py`, `watch_store.py`) reads and writes watches via **GitHub Gist**, not HTTP to `/_api/watches`. Internal ops may use `scripts/smoke_test_api.py` against `https://magictablefinder.com/_api` with `API_SECRET`. No VPS code changes are required for this migration.

## Secrets and environment variables

Set these in **Cloudflare Pages → Settings → Environment variables** (Production and Preview as appropriate). Mark sensitive values as **Encrypted**.

### Required for consumer auth

| Variable | Purpose |
| --- | --- |
| `MAGIC_LINK_SECRET` | HMAC secret for magic-link + session cookies (≥32 chars) |
| `RESEND_API_KEY` | Resend API key for magic-link email |
| `MAGIC_LINK_FROM` | Resend `from` address (e.g. `Magic Table Finder <noreply@…>`) |
| `URL` | Canonical site origin, e.g. `https://magictablefinder.com` (also set on custom domain; preview can rely on request origin if omitted) |

### Internal / legacy API auth (Craig & Jessica)

| Variable | Purpose |
| --- | --- |
| `API_SECRET` | Legacy shared secret fallback |
| `WATCH_USERS` | JSON map of internal users (`craig`, `Jessica`) with `password` + `phone` |
| `DEFAULT_OWNER_ID` | Default owner when omitted (default `craig`) |
| `DEFAULT_OWNER_NAME` | Display name fallback |
| `FALLBACK_USERS` | Used when `WATCH_USERS` unset (no phones) |

### Stripe billing

| Variable | Purpose |
| --- | --- |
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret for `POST /_api/billing/webhook` |
| `STRIPE_PRICE_SINGLE_WATCH` | Price ID for one-off watch checkout |
| `STRIPE_PRICE_PLANNER` | Price ID for Planner subscription |

### Gist (watches, bot state, calendars)

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | Token with gist read/write |
| `GITHUB_GIST_ID` | Production gist ID |

### Optional tuning

| Variable | Purpose |
| --- | --- |
| `HEALTH_STALE_MINUTES` | `/ _api/health` staleness threshold (default `30`) |
| `PLANNER_WATCH_CAP` | Max active billable watches for Planner (default `4`) |
| `CONSUMER_ACTIVE_WATCH_BUDGET` | Global consumer watch row cap |
| `MTF_USER_STORE` | `memory` (tests only); production uses KV binding automatically |
| `CF_PAGES_URL` | Optional; fallback canonical URL on Pages previews |

### GitHub Actions (repository secrets)

| Secret | Purpose |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Token with Pages + KV edit (for deploy workflow) |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

For one-off blob migration (run locally, not in CI):

| Variable | Purpose |
| --- | --- |
| `NETLIFY_AUTH_TOKEN` | Netlify personal access token |
| `NETLIFY_SITE_ID` | `b1f7efc5-da94-4159-ade0-568de33ed24f` (default in export script) |

### KV binding (not an env var)

In `wrangler.toml`, replace placeholder IDs and create namespaces in the dashboard:

- Binding name: **`MTF_USERS`**
- Production namespace id → `id = "REPLACE_WITH_PRODUCTION_KV_NAMESPACE_ID"`
- Preview namespace id → `preview_id = "REPLACE_WITH_PREVIEW_KV_NAMESPACE_ID"`

## Cutover checklist (in order)

1. **Review and merge this PR** only when ready to migrate (merge enables Cloudflare deploy on `main` via `deploy-cloudflare.yml`; Netlify push deploy is disabled).
2. **Add GitHub secrets** `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
3. **Create Cloudflare Pages project** `magictablefinder` (if not exists) linked to this repo, or rely on `wrangler pages deploy` from Actions.
4. **Create KV namespaces** (production + preview). Paste IDs into `wrangler.toml` and commit if needed, or configure in the dashboard to match binding `MTF_USERS`.
5. **Set all Pages environment variables** listed above (Production; mirror to Preview for testing).
6. **Export Netlify Blobs** (one-off, from a trusted machine with Netlify token):
   ```bash
   NETLIFY_AUTH_TOKEN=… NETLIFY_SITE_ID=b1f7efc5-da94-4159-ade0-568de33ed24f \
     node scripts/export-netlify-blobs.mjs --out ./netlify-blobs-export.json
   ```
7. **Import into KV** (after KV IDs are in `wrangler.toml` and wrangler is authenticated):
   ```bash
   node scripts/import-to-kv.mjs --file ./netlify-blobs-export.json --store mtf-users
   ```
8. **Deploy to Cloudflare** (push to `main` or run **Deploy to Cloudflare Pages** workflow).
9. **Test on `*.pages.dev`** (and custom domain when attached):
   - Sign-in magic link (Resend)
   - `GET /_api/auth/me`, create watch, delete watch
   - Stripe test checkout + `POST /_api/billing/webhook` (Stripe CLI or dashboard test event)
   - `GET /_api/health`, `GET /_api/profiles` (smoke script with secrets)
10. **Update Stripe webhook endpoint** if the public host changes (same path: `https://<host>/_api/billing/webhook`).
11. **DNS (Cloudflare DNS)** — only after Pages tests pass:
    - Apex `magictablefinder.com`: replace Netlify A records with Cloudflare Pages custom domain (CNAME flattening / Pages recommended setup).
    - `www`: CNAME to Pages (replace `disney-dining-bot.netlify.app`).
12. **Verify production** (sign-in, watch, billing, health).
13. **Cancel Netlify** subscription/site (manual; out of scope for this PR).

## Deploy workflows

| Workflow | Trigger | Target |
| --- | --- | --- |
| `.github/workflows/deploy-cloudflare.yml` | Push to `main`, `workflow_dispatch` | Cloudflare Pages |
| `.github/workflows/deploy.yml` | **`workflow_dispatch` only** | Netlify (legacy; avoids double deploy) |

## Local development

```bash
cp public/restaurants.json functions/lib/restaurants.json
cd functions && npm install
npx wrangler pages dev ../public --compatibility-flags=nodejs_compat
```

## Known differences vs Netlify

- **Storage:** KV replaces Blobs for `mtf-users`. Key layout is identical; `claimNonce` / email upsert races use KV get-then-put (same practical semantics as Blobs `onlyIfNew`).
- **Runtime:** Pages Functions use the Workers runtime with `nodejs_compat` for Stripe’s fetch HTTP client and `constructEventAsync` on webhooks.
- **Magic link base URL:** Derived from request origin when `URL` is unset (good for `*.pages.dev`); set `URL` in production to `https://magictablefinder.com`.
- **Netlify Blobs `connectLambda`:** Still supported in shared code for emergency Netlify rollback via manual `deploy.yml` dispatch only.
