---
name: world-class-ux
description: Designs, critiques, and implements polished consumer-grade UX for Magic Table Finder. Use when improving frontend flows, reservation watch creation, onboarding, empty states, status messaging, multi-user behavior, or when the user asks for a world class UX experience.
---

# World Class UX

## Mission

Make Magic Table Finder feel like a trustworthy alert product, not a scraper dashboard.

The core job is simple:

1. Know who is signed in (`#profile-label`).
2. Browse restaurants, then create a precise dining alert.
3. Understand what is being watched.
4. Trust the bot is running.
5. Act fast when an alert arrives.

Everything in the UX should reduce doubt around those five moments.

## Product Principles

- Lead with restaurant browse, then create an alert. The availability calendar is a supporting tool, not the home surface.
- Use plain language: "Watch", "Alert me", "Party", "Date", "Time window", "Any meal".
- Make ownership obvious. The session chip shows who is signed in; Craig and Jessica should never wonder whose watch or phone will receive alerts.
- Prefer guided inputs over free text where practical. If free text is used, validate immediately and explain how to fix it.
- Treat bot health as user trust. Show whether the worker is running, when it last polled, and whether there are actionable issues.
- Keep alert criteria visible everywhere: restaurant, date, party size, meal period, time window, owner.
- Avoid false precision. If Disney says no availability or a date is not bookable yet, say that clearly.
- Design for mobile first; this will often be used quickly on a phone.

## UX Workflow

When asked to improve UX:

1. Identify the user's current task and emotional state.
2. Walk the existing UI path in code before proposing changes.
3. List the top friction points in order of user impact.
4. Make the smallest shippable improvement that noticeably reduces friction.
5. Validate the create-watch, delete-watch, status, and profile flows.
6. Keep changes deployable: no mock-only UI unless explicitly requested.

## Magic Table Finder Acceptance Criteria

A UX change is not done until these are true:

- Session chip (`#profile-label`) shows the signed-in identity.
- Empty My Watches copy is `No watches yet. Browse restaurants`, with a control that opens the Restaurants tab.
- Watch creation can be completed with the calendar-first date picker, with manual date entry available as a secondary option.
- Watch creation supports restaurant, party size, one or more dates, meal period, and optional time window.
- Created watches appear under the correct owner.
- Watches can be deleted, including generated `watch_...` IDs.
- Empty states tell the user what to do next.
- Errors explain the problem and the next action.
- All watch creation flows must require an explicit, unchecked SMS consent checkbox to comply with Twilio A2P 10DLC requirements.
- The status area distinguishes healthy, needs attention, and stale/unknown states.
- The UI remains usable on a phone-sized viewport.
- Mobile date picking has an obvious open action and an obvious `Done`/close action.

## Copy Standards

Use copy like:

- "Create Watch"
- "Alert me when this opens"
- "Choose Dates"
- "Done"
- "Enter dates manually"
- "Any meal"
- "Earliest time"
- "Latest time"
- "Last checked 10:42 PM"
- "No watches yet. Browse restaurants"
- "Sign out"
- "Pay $4.99 and watch"
- "Disney has not opened booking for this date yet."

Avoid copy like:

- "grey dates" without explaining what action to take
- "scrape"
- "config"
- "facility ID"
- "HTTP 404"
- "session error" without a next action

## Implementation Guardrails

- Do not break the Netlify API contract: `/_api/profiles`, `/_api/status`, `/_api/restaurants`, `/_api/watches`.
- Preserve owner scoping through `X-User-Id`.
- Do not expose phone numbers, secrets, tokens, or Gist details in the frontend.
- Do not make calendar cache availability a prerequisite for watch creation.
- Do not add heavy frameworks to `public/index.html` unless the user explicitly approves a frontend rewrite.
- Prefer progressive enhancement in the existing single-page app.

## Validation Checklist

Run or request these checks before calling a UX change done:

```bash
node --check netlify/functions/api.js
PYTHONPYCACHEPREFIX=.pycache python3 -m unittest tests.test_alert_semantics
PYTHONPYCACHEPREFIX=.pycache python3 -m py_compile disney_bot.py monitor.py notify.py watch_store.py update_calendar_cache.py seed_disney_session.py
```

For production-impacting changes, smoke test:

- `GET /_api/profiles`
- `GET /_api/status` for Craig and Jessica
- Create and delete a non-real future watch for each affected owner, then clean it up
- Confirm VPS timer is active when worker behavior is touched

## Review Stance

When reviewing UX work, prioritize:

1. Main workflow breakage.
2. Ownership or alert-routing confusion.
3. Missing validation or unclear errors.
4. Mobile usability issues.
5. Visual polish.

Report blockers first, then improvements. If no blockers, say so plainly and name the remaining polish opportunities.
