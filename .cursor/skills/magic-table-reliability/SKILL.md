---
name: magic-table-reliability
description: Reviews and improves Magic Table Finder reliability. Use when working on polling, notification delivery, VPS/systemd deployment, bot health, Gist state, dedupe, error handling, or production smoke tests.
---

# Magic Table Reliability

## Mission

Keep Magic Table Finder boringly reliable: watches are polled remotely, alerts go to the right owner, failures are visible, and duplicate/spurious alerts are avoided.

## Reliability Priorities

1. Do not lose a real alert.
2. Do not spam duplicate alerts.
3. Do not mark failed sends as successful.
4. Do not let one restaurant failure poison the whole poll.
5. Do not hide stale worker/session state.
6. Do not expose secrets or phone numbers in frontend/API responses.

## Review Checklist

- Watches are owner-scoped from API request through worker alert.
- Generated `watch_...` IDs work for create and delete.
- Disney `404` availability responses are handled as no availability, not bot failure.
- Future dates outside Disney's booking window are skipped without marking the session unhealthy.
- Notification failures are caught, logged, and reflected in `bot_state.json`.
- `last_sms_sent_at` only advances after a successful send.
- `open_slots.json` is the primary new-opening baseline. Continuously open slots must stay quiet; disappeared-and-reopened slots should alert.
- `seen_slots.json` is alert history/audit only and is updated only after successful notification delivery.
- Stable alert identity excludes Disney `offerId`; include `offerId` in booking links but not dedupe keys.
- Failed restaurant polls preserve that restaurant's previous `open_slots.json` baseline so the next successful poll does not spam old openings.
- Partial notification failures are visible in `bot_state.json`, and failed recipient slots stay eligible to retry.
- The VPS timer is the only production poller; the old Mac LaunchAgent stays disabled.
- **Twilio A2P Compliance**: All alerts must append `Reply STOP to opt out. Reply HELP for help.` to avoid carrier blocking.

## Validation Commands

```bash
node --check netlify/functions/api.js
PYTHONPYCACHEPREFIX=.pycache python3 -m unittest tests.test_alert_semantics
PYTHONPYCACHEPREFIX=.pycache python3 -m py_compile disney_bot.py monitor.py notify.py watch_store.py update_calendar_cache.py seed_disney_session.py
```

Production smoke checks:

- `GET /_api/profiles`
- `GET /_api/status` for `craig` and `Jessica`
- `GET /_api/watches` for `craig` and `Jessica`
- Create/delete a clearly fake future watch, then verify cleanup
- `systemctl is-active disney-dining-bot.timer` on the VPS

## Deployment Rules

- Commit only reviewed, validated changes.
- Push `cursor/self-hosted-mousewatcher`.
- Push `HEAD:main` for website/API changes so Netlify deploys production.
- Sync VPS to the pushed commit for worker changes.
- Trigger Netlify deploy for website/API changes.
- Smoke-test production after deploy.
- Pause the VPS timer before validating risky alert-state changes; re-enable it only after a quiet/manual poll or deliberate baseline.
