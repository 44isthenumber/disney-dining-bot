# Tournament score

Judged from live local mocks (ports 8788 / 8789 / 8790) plus desktop and mobile screenshots. Scale 1–5. Ties break on Confidence, then Product honesty.

| Criterion | Quiet Luxury | Park Day Pulse | Trusted Watch |
|---|---|---|---|
| Confidence | 4 | **5** | 4 |
| Product honesty | 5 | 5 | 5 |
| Mobile | 3 | 4 | 3 |
| Implementable | 3 | 4 | **5** |
| Not-Disney | 5 | 5 | 5 |
| Logged-in coherence | 4 | **5** | 5 |
| **Total** | **24** | **28** | **27** |

## Winner: Park Day Pulse

A trip planner’s confidence is “I will get the text when the table opens.” Park Day Pulse puts that SMS on the hero — California Grill, 7:15 PM, STOP language — before explaining the mechanism. The logged-in chrome keeps the same temperature: owner callout (“Craig’s watch → Craig’s phone”), lime primary actions, coral for new openings, health preview.

Trusted Watch is the closest restyle of today’s SPA and the most honest ops-facing product. It loses the landing-page job: it still reads like a competent tool, not a badass public face.

Quiet Luxury is the most distinct brand, and the copy is excellent. It reads like a hotel more than an alert product, and the sticky header crowds badly at ~390px.

## Disqualifiers

None. All three kept vanilla HTML, live legal URLs, shared fixtures, unchecked SMS consent on Create Watch, no fake metrics, no castle logo.

## Notes

- Quiet Luxury pre-fills a demo password on the landing form (mock-only; do not carry into production).
- Trusted Watch’s hero diagram labels the middle step “Poll” — accurate internally, slightly ops-y for a public face.
- Park Day Pulse mobile hero is dense (lime + coral + phone). Keep the phone mock; tighten the sticky header so the locked promise still reads on a phone.

## What ships next

Implement Park Day Pulse into `public/index.html` on this feature branch (not `main`):

1. Replace the castle-emoji login overlay with the Park Day Pulse landing + existing Craig/Jessica sign-in fields.
2. Restyle post-login chrome (header, create-watch, watch cards, health) to the same navy / lime / coral system.
3. Keep `/_api/*` wiring, SMS consent, calendar-first dates, and owner scoping unchanged.
