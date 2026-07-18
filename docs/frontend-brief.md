# Frontend brief — Miha

Your scope: **PWA + app screens + landing page.** You build against live endpoints;
`/api/state` and `/api/profile` are real now, `/api/chat` you stub until it lands.
Full context: [roadmap.md](roadmap.md). Contract is frozen — if you need a shape
changed, flag it and we change it on the backend in the same PR.

## Run the backend locally
```bash
cd cp-advisor
pip install fastapi uvicorn        # if not already
python3 -m uvicorn backend.main:app --reload --port 8000
# open http://localhost:8000/api/state
```
The frontend `API` base points at this. Everything is static + CORS-free on the same host.

## Live endpoints (build against these)

### `GET /api/state` — dashboard
```json
{
  "persona": { "name": "Marko Novak", "city": "Ljubljana", "household": "..." },
  "household": { "city": "Ljubljana", "hasCar": true, "carFinancing": "owned_outright",
                 "homeOwnership": "tenant", "lineCount": 1, "dependentsAndDebt": {} },
  "currentSubscriptions": [
    { "vertical": "telco", "kind": "mobile", "provider": "A1", "planName": "A1 MaksiMIO ...", "monthlyEur": 27.99, "attributes": { "dataGB": 500 }, "switchable": true },
    { "vertical": "water", "kind": "water", "provider": "JP VOKA Snaga", "planName": "Municipal water + sewage", "monthlyEur": 22.0, "attributes": {}, "switchable": false }
  ],
  "totals": { "monthlyEur": 212.87, "byVertical": { "telco": 88.97, "energy": 41.9, "insurance": 60.0, "water": 22.0 } }
}
```
- Dashboard tiles = group `currentSubscriptions` by `vertical`; show the big total (`totals.monthlyEur`) up top.
- `kind` is the explicit line role; `household` is shared facts (display or ignore).
- `switchable: false` (water) → show as info-only, no "find a better deal" CTA.

### `POST /api/profile?vertical=telco` — the needs card (the money shot)
Body optional for the demo (falls back to the canned Marko profile). Returns `{ profile, offer }`.
Render the `offer`:
```json
{
  "currentMonthlyEur": 88.97,
  "recommendedMonthlyEur": 63.98,
  "monthlySavingsEur": 24.99,
  "annualSavingsEur": 299.88,
  "recommendation": {
    "mobile": {
      "toName": "zeleni bob", "toOperator": "BOB", "toMonthlyEur": 7.99,
      "why": "placujes 27.99 eur za 500 GB, porabis pa okoli 15 GB, zeleni bob (BOB) ti da dovolj hitrih podatkov za 7.99 eur"
    }
  },
  "dontPayFor": [
    { "name": "A1 Arena Sport Premium (TV channel add-on)", "monthlyEur": 4.99,
      "why": "za A1 Arena Sport Premium ... sporta pa ne gledas - cista izguba" }
  ],
  "notes": []
}
```
Render rules:
- Hero number = `monthlySavingsEur` ("prihranis 24,99 EUR / mesec"). If it's `null`, show the trade-off / advisory instead of a savings number — never render `null` as `0`.
- `dontPayFor[]` = red "nehaj placevati" cards; show each `why`.
- `recommendation` is a bag keyed by type: telco → `recommendation.mobile`; energy →
  `recommendation.electricity` (`.tradeoff` or `.cheapest`) + optional `.gas` / `.dualFuel`;
  insurance → `null`. Each sub-object has its own `why`. Render green "zamenjaj" cards.
- `notes[]` = grey assumption footnotes (e.g. energy "no usage" case).
- `?explain=false` returns the same numbers with no `why` — use the default (with `why`).

Try the other verticals too: `?vertical=energy` (trade-off, `monthlySavingsEur: null`),
`?vertical=insurance` (35 EUR droppable). Handle all three shapes.

### `POST /api/chat` — LIVE (streaming)
`POST /api/chat?vertical=<v>` body `{ history:[{role,text}] }` → `text/event-stream`.
POST, so use `fetch` + a ReadableStream reader (not `EventSource`). Frames are SSE
`data:` lines carrying JSON:
- `{"type":"token","text":"..."}` — append as it arrives (first token ~2s).
- `{"type":"error","message":"..."}` — soft notice; a fallback token was already streamed, don't hard-fail.
- `{"type":"done","full":"..."}` — terminal (always fires); `full` = complete reply to push into history.
Render the typing indicator the instant send is tapped; stop it on `done`.

### `POST /api/lead` — STUB for now
`{ vertical, history }` → `{ ok, leadId }`. Wire the "book" button to it; Zan makes it real.

## Task checklist
**PWA plumbing**
- [ ] `manifest.json` (name "Frugl", standalone, theme color, start_url)
- [ ] service worker: precache the app shell + vendored CSS, offline fallback screen
- [ ] app icons (192/512) + splash, add-to-home-screen prompt
- [ ] Lighthouse PWA pass (installable, works offline for the shell)

**App screens** (mobile-first, one column)
- [ ] Onboarding (short: the anti-upsell promise)
- [ ] Dashboard: vertical tiles + total spend, from `/api/state`
- [ ] Chat: SSE consumer, typing indicator fires the instant you tap send
- [ ] Needs card: render `offer` (savings + dontPayFor + recommendation + notes)
- [ ] Book confirm → `/api/lead` → done screen

**Landing page** (separate static page)
- [ ] Anti-upsell thesis, before/after, waitlist / CTA. Reuse the vendored styling.

## Copy + design rules
- All Slovenian copy **without sumniki** (write `c/s/z`, never `č/š/ž`) — matches the backend.
- Mobile-first; instant UI (render the shell immediately, spinners for anything > 1s).
- The thesis is trust: show the *saving* and the *why*, never a hard upsell.
