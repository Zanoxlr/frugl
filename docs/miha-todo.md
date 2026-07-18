# TODO for Miha's AI — Frugl frontend

You are building the **frontend** for Frugl: a mobile-first B2C app that shows a
Slovenian user all their utility subscriptions, lets them talk to a grounded AI
advisor, and shows a right-fit offer WITHOUT upselling. This is a hackathon POC.

**Your lane:** only touch `frontend/` and a new `landing/` folder. Do NOT edit
`backend/`, `data/`, `tests/`, or `prompts/` — that's the other developer's lane.
The API contract is frozen; if you think a response shape must change, STOP and
leave a note in your PR description instead of editing the backend.

Read `docs/frontend-brief.md` (full endpoint examples) and `docs/roadmap.md` (contract)
first. This file is the ordered task list.

## Run the backend to develop against
```bash
cd cp-advisor
pip install fastapi uvicorn
python3 -m uvicorn backend.main:app --reload --port 8000
```
`/api/state` and `/api/profile` are LIVE. `/api/chat` and `/api/lead` are NOT built
yet — stub them locally (see task 4).

## Live endpoints (already work — build against THESE exact shapes)
- `GET  /api/state` → `{ persona, household, currentSubscriptions[], totals }`.
  `persona`: `{ name, city, household }` (that `household` is a text blurb, display only).
  `household` (the object): shared facts `{ city, hasCar, carFinancing, homeOwnership, lineCount, dependentsAndDebt }`.
  each line: `{ vertical, kind, provider, planName, monthlyEur, attributes, switchable }`
  where `kind` is the explicit line role (telco: `fixed`/`mobile`/`tv_addon`; energy:
  `electricity`; insurance: `legacy_dopolnilno`/`car_ao`; water: `water`).
  `totals`: `{ monthlyEur, byVertical }`. Group tiles by `vertical`.
- `POST /api/profile?vertical=telco` → `{ profile, offer }`. Render `offer`:
  `{ currentMonthlyEur, recommendedMonthlyEur, monthlySavingsEur, annualSavingsEur,
     recommendation, dontPayFor[], notes[] }`. Each `dontPayFor` and the
  `recommendation.mobile` have a `why` string. Verticals: `telco`, `energy`, `insurance`.
  IMPORTANT: `monthlySavingsEur` can be `null` (energy no-usage case) — render the
  trade-off / advisory text then, never show `null` as `0`.

## `POST /api/chat` — LIVE (streaming)
`POST /api/chat?vertical=telco` body `{ history:[{role,text}] }` → `text/event-stream`.
It's POST, so use `fetch` + a stream reader (NOT `EventSource`, which is GET-only).
Frames are SSE `data:` lines, each a JSON object:
- `data: {"type":"token","text":"..."}` — append `text` to the current bubble as it arrives.
- `data: {"type":"error","message":"..."}` — a soft failure notice (a fallback token was already sent). Don't hard-fail the UI.
- `data: {"type":"done","full":"..."}` — terminal; `full` is the complete reply (use it to push the finished turn into `history`).
`done` ALWAYS fires (even on error), so key your "stop typing indicator" on it. First
token lands ~2s after send; render the typing indicator instantly on send.

## Not built yet — stub `/api/lead` (task 5)
- `POST /api/lead` `{vertical, history}` → `{ ok, leadId }`. Wire the button; stub the response.

## Tasks (in order, commit each)

1. **Dashboard** — `GET /api/state`. Group `currentSubscriptions` by `vertical` into tiles,
   show the big monthly total (`totals.monthlyEur`) on top. `switchable:false` (water)
   shows as info-only, no CTA. Acceptance: tiles + total render from live data on a phone viewport.

2. **Needs card** — after a vertical is picked, `POST /api/profile?vertical=<v>`.
   Render the `offer`: hero = `monthlySavingsEur` ("prihranis X EUR/mesec"), red
   "nehaj placevati" cards from `dontPayFor[]` (show each `why`), green "zamenjaj"
   card from `recommendation` (show `why`), grey footnotes from `notes[]`. Handle the
   `null` savings case. `recommendation` is a bag keyed by type — telco has
   `recommendation.mobile`; energy has `recommendation.electricity` (with either a
   `tradeoff` or a `cheapest`) and optionally `recommendation.gas` / `recommendation.dualFuel`;
   insurance has `recommendation: null` (value is all in `dontPayFor`). Each sub-object
   carries its own `why`. Acceptance: all three verticals render without error, including
   energy's `null`-savings trade-off.

3. **Chat screen** — SSE consumer for `/api/chat`. Typing indicator fires the INSTANT
   send is tapped (optimistic UI). Append streamed tokens as they arrive. Acceptance:
   against the stub, tokens stream into the bubble; send feels instant.

4. **Local stubs** — a tiny dev mock for `/api/chat` (SSE, canned reply) and `/api/lead`
   (`{ok:true, leadId:"stub"}`), toggled by an env/const so it's trivial to remove once
   the real endpoints land. Acceptance: full flow works with the backend running,
   even though chat/lead are backend-stubbed.

5. **Book flow** — "book" button → `POST /api/lead` → done screen. Acceptance: tapping
   book reaches the done screen.

6. **PWA** — `manifest.json` (name "Frugl", `standalone`, theme color, start_url),
   service worker (precache the app shell + vendored CSS, offline fallback screen),
   icons (192/512) + splash, add-to-home-screen prompt. Acceptance: Lighthouse marks it
   installable and the shell loads offline.

7. **Landing page** — new `landing/` static page: the anti-upsell thesis, a before/after,
   a waitlist / CTA. Reuse the vendored styling. Acceptance: standalone page loads, mobile-first.

## Hard rules
- All Slovenian copy **without sumniki**: write `c/s/z`, never `č/š/ž` (e.g. "cas" not "čas").
- Mobile-first, one column. Instant UI: render the shell immediately, spinner for anything > 1s.
- **Vendored CSS/JS only, no CDN** (must work offline as a PWA).
- The thesis is trust: show the saving and the `why`, never a hard upsell.
- Don't invent backend behavior. If the data isn't in `/api/state` or `/api/profile`,
  ask the backend dev — don't fake it in a way that hides a missing endpoint.
