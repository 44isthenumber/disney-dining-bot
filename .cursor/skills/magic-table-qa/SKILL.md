---
name: magic-table-qa
description: Performs focused QA for Magic Table Finder. Use when testing profile login, create-watch, delete-watch, status, production API smoke tests, or when asked to verify the product end to end.
---

# Magic Table QA

## Mission

Prove the product works from a user's point of view without leaving test data behind.

## Test Mindset

Test the real workflow:

1. Select a profile.
2. Create a precise watch.
3. See it under the correct owner.
4. Delete it.
5. Confirm the worker health remains OK.

Prefer safe fake future dates like `2099-01-01` for create/delete smoke tests, and always clean them up.

## Core Scenarios

- Profiles endpoint returns `craig` and `Jessica`.
- Craig sees only Craig watches.
- Jessica sees only Jessica watches.
- Creating a watch with invalid date/time returns a helpful error.
- Creating a valid watch returns generated `watch_...` IDs.
- Deleting generated IDs works.
- Status shows `ok` for both users when the worker is healthy.
- Restaurant search returns expected matches.

## Safety Rules

- Never print secrets, full phone numbers, tokens, or `.env` contents.
- Never leave fake watches behind.
- Do not send real SMS unless explicitly asked.
- If a test creates production data and cleanup fails, report the watch ID immediately.

## Useful Smoke Test Shape

Use the live API with `X-API-Secret` and `X-User-Id`; create a fake future watch; verify it appears; delete it; verify it is gone.

Report:

- Endpoint status codes
- Created watch IDs
- Cleanup status
- Remaining watches for the tested owner
- Any production health change
