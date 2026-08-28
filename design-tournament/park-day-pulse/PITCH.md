# Park Day Pulse

## Audience

Craig or Jessica is moving through a park day with a phone in a pocket and a dining plan in mind. They do not want another planning dashboard. They want to trust that a precise watch is active, know which profile will receive the alert, and recognize the useful SMS the instant it arrives.

## Art direction (type, color, motion)

Park Day Pulse uses Outfit for tightly packed, high-temperature headlines and DM Sans for direct product copy. Night navy (`#0B1220`) gives the alert moment focus; white cards keep forms familiar and fast; signal lime (`#C8F31E`) is reserved for primary actions; hot coral (`#FF5A36`) marks only the newly opened moment and owner-routing cues. The grid is dense, aligned, and designed around large phone tap targets. The only looping motion is a restrained ring from the SMS unread dot, with a reduced-motion fallback.

## Why this earns trust

The hero shows the product outcome before explaining the mechanism: the shared California Grill SMS is the largest visual proof. The language consistently says “new matching opening,” never every available table. The watch fixture is placed beside its resulting text so the causal relationship is obvious. The logged-in view keeps Create Watch first, makes the owner route unmissable, starts SMS consent unchecked, and gives health states calm, plain-language treatments. Legal and opt-out language stays close to the alert experience.

## What we would not ship

- No castle, characters, maps, official marks, or Disney-coded purple and blue.
- No fabricated reservation counts, customer totals, success rates, or guarantees.
- No live availability board, hype countdown, confetti, shake, or sneaker-drop urgency.
- No phone numbers, infrastructure language, internal identifiers, or production API calls.
- No SMS opt-in at sign-in and no consent checkbox that starts checked.

## Implementability notes for `public/index.html`

The vision is vanilla HTML, shared CSS, and small DOM scripts with no build step or framework. The landing sections can be introduced around the existing authenticated SPA, while the app visual system maps onto the current profile header, create-watch fields, date modal, health response, and owner-scoped watch list. The custom calendar is intentionally simple: it demonstrates multi-date selection, month navigation, chips, explicit Done, and manual entry without imposing a new application architecture. Static fixtures and interactions in this tournament folder do not call `/_api/*`.
