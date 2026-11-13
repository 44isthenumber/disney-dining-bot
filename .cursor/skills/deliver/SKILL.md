---
name: deliver
description: Magic Table Finder delivery loop — grok-4.7 strategy and verification, grok-4.7 builds, composer-2.5 mechanical work. Use on any multi-file or feature change. Cloud and iOS must follow this file; do not depend on laptop-only paths.
---

# /deliver (Magic Table Finder)

Agents grapple. Craig is not in the loop except redlines. Allowed models are `grok-4.7` and `composer-2.5` only. Do not launch Slack.

## Skip

Typos, single-file bug fixes with a clear repro, copy tweaks, or Craig said "just do it."

## Seats (different model each time)

| Seat | Model | Job |
|---|---|---|
| Spec | `grok-4.7-high` or `grok-4.7-xhigh` | Strategy. User story, testable AC, out of scope, files-that-will-change |
| Spec verify | `grok-4.7-xhigh` | Verification. Fresh subagent. Try to break the spec. Cite paths. |
| Build | `grok-4.7-low` or `grok-4.7-medium` | Stay inside the files list. Tests for every AC. |
| Mechanical | `composer-2.5` | Edits, formatting, and other mechanical work |
| QA | `grok-4.7-high` | Verification. Run the gate. Falsify AC. |
| Validator | `grok-4.7-xhigh` | Verification. Fresh. Credit for refuting. Never saw the build being made. |

Two fails in a row → stop and tell Craig.

## Gates after build

```bash
python3 -m unittest tests.test_alert_semantics
```

Frontend changes: extract the script from `public/index.html` and `node --check`.

## After validator pass

Stay off `main` unless Craig said deploy. A merge to `main` deploys Netlify.

## Redlines

Auth, Twilio, VPS, Gist, Disney session, secrets, destructive git. Cloud must not seed the Disney session, SSH to the VPS, or run the poller.

## Other lanes

- Social / X / out-of-repo agents → Grok Bot
- Mentions, phone, framing → Buzz (Fizz is voice, not captain)
