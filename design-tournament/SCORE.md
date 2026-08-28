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

## Rubric winner: Park Day Pulse

Agent judging preferred Park Day Pulse (28) over Trusted Watch (27) and Quiet Luxury (24). That score still stands as a record of the bake-off.

## Craig pick: Quiet Luxury (visual base)

Craig overrode the rubric. **Quiet Luxury is the style we implement** — paper, dusk ink, gold, Fraunces, plate-rim atmosphere, headline “The table is being watched.”

Copy in the Quiet Luxury mock is **not** locked. Drop hotel/ops jargon (“The Method,” “bespoke,” “battery remain undisturbed,” “alert semantics,” pre-filled demo password). Keep product-honest language from the brief: Watch, Alert me, newly opens, no table guarantee.

## Disqualifiers

None. All three kept vanilla HTML, live legal URLs, shared fixtures, unchecked SMS consent on Create Watch, no fake metrics, no castle logo.

## Notes

- Quiet Luxury mock pre-fills a demo password (mock-only; not carried into production).
- Quiet Luxury sticky header crowded at ~390px in the mock. Production restyle keeps the locked promise readable (wrap; do not hide the sentence).
- Trusted Watch’s hero diagram labels the middle step “Poll” — accurate internally, slightly ops-y for a public face.
- Park Day Pulse mobile hero is dense (lime + coral + phone). Kept as a competing vision, not the ship target.

## What ships next

Quiet Luxury restyle of `public/index.html` on this feature branch (not `main`):

1. Unauthenticated first screen is the Quiet Luxury landing; sign-in uses existing `#login-*` IDs and `/_api/status`.
2. Post-login chrome uses the same paper / ink / gold system. Do not remap `--blue`.
3. Keep `/_api/*` wiring, SMS consent, calendar-first dates, and owner scoping unchanged.
4. Stay off `main` until Craig says deploy.
