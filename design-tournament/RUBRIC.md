# Scoring rubric

Score each vision 1–5 on every row. Winner is highest total. Ties break on **Confidence**, then **Product honesty**.

| Criterion | 1 | 3 | 5 |
|---|---|---|---|
| **Confidence** | Looks like a side project or a booking scam | Pretty, but I would hesitate to trust it with a trip | A trip planner would believe the table watch is in competent hands |
| **Product honesty** | Feels like an availability dashboard, scraper, or Disney clone | Mostly right, with leftover ops jargon or a false guarantee | Clearly an alert product for *new* matching openings; owner-scoped; no fake metrics |
| **Mobile** | Hero or create-watch breaks under ~390px | Usable with awkward wrapping | Hero, sign-in, and create-watch feel designed for a phone |
| **Implementable** | Needs a framework, image library, or a new app architecture | Doable in vanilla HTML with some compromise | Can restyle `public/index.html` without a rewrite |
| **Not-Disney** | Castle logo, official marks, “guaranteed reservation,” character art | Disney-adjacent clichés (sparkles, purple fireworks) that still read as fan-site | Distinct brand. Names the parks as the domain without impersonating them |
| **Logged-in coherence** | Landing and app feel like two products | Same colors, different hierarchy | Landing promise continues into create-watch, health, and owner clarity |

## Disqualifiers (score 0 for the vision if any are true)

- Production API calls or secrets
- React/Vue/Svelte or a CSS framework CDN as the design system
- Castle-as-logo or official Disney marks
- Fake quantitative metrics
- Missing SMS consent on the create-watch mock
- Missing Privacy / Terms / SMS consent footer links (live magictablefinder.com URLs)
- Phone numbers or internal IDs shown
- Sign-in implies SMS opt-in (consent belongs on Create Watch)
- Per-card owner column that implies a cross-owner household dashboard

## Judging note

Pick on confidence for a trip planner, not which header is prettiest.
