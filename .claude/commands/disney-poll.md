# /disney-poll — Check Disney Dining Availability

Check current Disney dining availability for all watched restaurants using the live browser. Results are shown immediately. Works independently of the LaunchAgent.

## Steps

1. **Read the watch list** — fetch `https://magictablefinder.com/_api/watches` using the `mcp__Claude_in_Chrome` tools with header `X-API-Secret: P2ssw0Rd_pass1ord`. Parse the JSON to get restaurant name, facility_id, slug, party_size, meal_periods, and dates for each watch entry.

2. **For each watched restaurant:**
   a. Navigate the Disney Chrome tab to `https://disneyworld.disney.go.com/dine-res/restaurant/{slug}` using `mcp__Claude_in_Chrome__navigate`
   b. Wait 6 seconds for the page to fully load (Akamai session warm-up)
   c. Read the auth token from Chrome's cookie store by running this JS in the tab:
      ```javascript
      sessionStorage.getItem('_bot_token') || ''
      ```
      If empty, get it from the `TPR-WDW-LBJS.WEB-PROD.token` cookie by running:
      ```javascript
      // The page itself sets this when loaded — check page state
      document.cookie
      ```
      Fall back to running `python3 -c "import browser_cookie3, base64, json, re, time; ..."` via Bash to extract from Chrome's cookie store (see auth.py `_get_token_from_chrome()` logic).
   
   d. Fetch availability for the watched dates using `mcp__Claude_in_Chrome__javascript_tool`:
      ```javascript
      (async () => {
        const token = sessionStorage.getItem('_bot_token') || 'BEARER {token_from_step_c}';
        const dates = {watched_dates};  // e.g. ['2026-06-01', '2026-06-07']
        const start = dates[0], end = dates[dates.length - 1];
        const partySize = {party_size};
        const fid = '{facility_id}';
        const resp = await fetch(
          `/dine-res/api/availability/${partySize}/${start},${end}?facilityId=${fid}&entityType=restaurant`,
          { headers: { 'Authorization': token, 'x-function-name': 'getAvailability',
                       'x-disney-internal-dine-vas-365': 'true', 'accept': 'application/json' } }
        );
        window._pollResult = { status: resp.status, data: resp.status === 200 ? await resp.json() : null };
      })(); 'fired'
      ```
   
   e. Wait 3 seconds then read `window._pollResult`.
   
   f. Parse slots from `data.restaurants` — for each date in watched dates, for each meal period, extract available times from `offersByAccessibility[*].offers[*]`. Filter to matching `meal_periods` if specified.

3. **Display results** in a clear table:
   ```
   Restaurant         | Date       | Meal     | Available Times
   -------------------|------------|----------|----------------
   Jaleo              | 2026-06-01 | DINNER   | 6:00 PM, 6:30 PM, 8:45 PM
   'Ohana             | 2026-06-07 | DINNER   | 5:00 PM, 7:15 PM
   ```
   If no slots found on any watched date, say so clearly.

4. **If slots are found**, ask the user:
   - "Want me to open the booking page for [restaurant] on [date]?"
   - If yes, navigate Chrome to the restaurant's booking URL: `https://disneyworld.disney.go.com/dine-res/book/table-service/details/{facility_id}/?date={date}&partySize={party_size}`

## Notes
- Chrome must be open with a `disneyworld.disney.go.com` tab
- "Allow JavaScript from Apple Events" must be enabled in Chrome (`View → Developer → Allow JavaScript from Apple Events`)
- The navigate-per-restaurant approach is required — making multiple API calls from one page gets Akamai 428 errors
- Token is valid for 24hrs and auto-refreshes from Chrome's cookie store
