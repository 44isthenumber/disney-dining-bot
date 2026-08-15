---
name: deliver
description: Magic Table Finder delivery loop — spec, second-model verify, Grok build, Gemini QA, GPT validator. Use on any multi-file or feature change. Replaces Fizz-captain / Claude Code. Cloud and iOS must follow this file; do not depend on laptop-only paths.
---

# /deliver (Magic Table Finder)

Agents grapple. Craig is not in the loop except redlines. Do not launch Claude Code, Goose, or Slack.

## Skip

Typos, single-file bug fixes with a clear repro, copy tweaks, or Craig said "just do it."

## Seats (different model each time)

| Seat | Model | Job |
|---|---|---|
| Spec | inherit (Grok) | User story, testable AC, out of scope, files-that-will-change |
| Spec verify | `composer-2.5-fast` | Fresh subagent. Try to break the spec. Cite paths. |
| Build | `cursor-grok-4.6-high-fast` | Stay inside the files list. Tests for every AC. |
| QA | `gemini-3.7-flash-high` | Run the gate. Falsify AC. |
| Validator | `gpt-5.6-terra-medium` as `verifier` | Fresh. Credit for refuting. Never saw the build being made. |

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
