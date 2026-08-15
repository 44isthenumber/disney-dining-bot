# Magic Table Finder — Agent Instructions

> **Primary law for Cursor and Grok Build.** Do not route work to Goose or Claude/Anthropic.
> `CLAUDE.md` is an archive of product detail. Prefer this file + `.cursor/rules/`.

## Product promise

Craig and Jessica get owner-scoped alerts on **new** matching openings. Not a dashboard of every open time.

Live site: magictablefinder.com.

## Stack (locked 2026-08-15)

| Layer | Tool | Notes |
|---|---|---|
| Owner | **Cursor** | Classify, integrate, verify, Cloud/iOS |
| Builder | **Grok 4.6 in Cursor** | Default coding model |
| QC | **Other Cursor LLMs** | `/deliver` — spec verify / QA / validator must differ from the builder |
| Social / agents | **Grok Bot** | Out-of-repo only. Not this repo's owner. |
| Communication | **Buzz** | Mentions and phone. Fizz frames, not captain. Never Slack. |
| Production poller | **VPS systemd timer** | Every 10 min. Headed Playwright under Xvfb. Not Cloud. |
| High-risk review | **Codex** | Auth, Twilio, VPS, Gist, destructive git |
| Goose / Claude Code | **Out** | Do not launch |

## Cursor Cloud specific instructions

Cloud clones GitHub `44isthenumber/disney-dining-bot`. It cannot see Mac Keychain, the VPS, or the Disney browser profile.

**Protect Disney authentication and availability over every other Cloud goal.** See `.cursor/rules/disney-session-protection.mdc`.

**Cloud may:** UI, Netlify functions, unit tests, docs, PRs.

**Cloud may not:** seed Disney session, SSH to the VPS, send Signal/Twilio, clear `open_slots.json` / `seen_slots.json`, run the poller, or deploy production.

- After alert/worker edits: `python3 -m unittest tests.test_alert_semantics`
- After frontend edits: extract the script from `public/index.html` and run `node --check`
- Do not `playwright install` or run `disney_bot.py` in Cloud. Headed Disney Chrome lives on the VPS.
- Do not add Cloud secrets for Disney login, Twilio, Signal, or a Gist write token. Code and unit tests do not need them.
- Do not change `DISNEY_HEADLESS`, recovery cooldown, navigate-per-restaurant, or refresh-failure handling unless Craig explicitly asks.

## Delivery

For anything beyond a typo or single-file fix, run `~/.cursor/skills/deliver/SKILL.md`. Agents grapple; do not ask Craig to approve the spec. After validator pass, stay off `main` (Netlify deploys from `main`). Cloud still must not touch the VPS Disney session.

## Safety

- Never mutate `.env`, Gist state, Twilio, Netlify, VPS, or git history unsupervised.
- Do not clear `open_slots.json` or `seen_slots.json` unless Craig asks for alert-state repair.
- Alert / worker / notification changes: run `tests/test_alert_semantics.py`.
- Frontend changes: `node --check` on extracted `public/index.html` script.
- Smoke-test with `scripts/smoke_test_api.py` before calling production work done.

## Commands

```bash
python3 -m pytest tests/test_alert_semantics.py
python3 scripts/smoke_test_api.py --user-id craig
```

## Key docs

| What | Where |
|---|---|
| Full product archive | `CLAUDE.md` |
| VPS deploy | `VPS_DEPLOYMENT.md` |
| Troubleshooting | `TROUBLESHOOTING.md` |
| Reliability skill | `.cursor/skills/magic-table-reliability/SKILL.md` |
