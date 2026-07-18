# Frugl — Roadmap & Work Split

Frugl is a mobile B2C anti-upsell advisor for Slovenian utilities. Understand your
bills → define your real needs with a grounded AI → get the right-fit offer (not the
fattest one) → hand over an honest, pre-constrained lead. Monetized per lead / affiliate.

## Where we are (2026-07)
Two engines exist, both public-safe, both proven; not yet wired into the app.

- **Advisor (LLM)** — `backend/llm.py`, `claude -p` OAuth subscription. Grounded chat +
  needs-profile extraction. 14/14 adversarial Qs correct, zero hallucinations.
- **Calculator (deterministic)** — `backend/{catalog,compare,reasons,main}.py`. Turns a
  needs profile into euro savings + a "don't pay for X" list, no LLM, instant. 23 tests
  green. `POST /api/compare/{vertical}`, `POST /api/compare-all`, `GET /api/demo-user`.

## The seam: API contract (both sides build against THIS)
The frontend and backend integrate only through these shapes. Agree changes here first.

| Endpoint | Request | Response |
|---|---|---|
| `GET /api/state` | – | `{ persona, household, currentSubscriptions[] (each with kind+attributes), totals }` |
| `POST /api/chat` | `{ vertical, history:[{role,text}] }` | **`text/event-stream`** — token-delta events, terminal `done` event |
| `POST /api/profile` | `{ vertical, history }` | `{ profile:<Preferences>, offer:<compare() result> }` |
| `POST /api/lead` | `{ vertical, history }` | `{ ok, leadId }` |

`offer` = the exact `compare()` result already shipped: `{ currentMonthlyEur,
recommendation, recommendedMonthlyEur, dontPayFor[], monthlySavingsEur,
annualSavingsEur, notes[] }`, with B2 `why` strings when `?explain=true`.

Contract rule: the backend owns these shapes; the frontend renders them. Any field
change goes here in the same PR, so neither side breaks silently.

## Decisions
- **Chat streams from day one** (SSE). Frontend builds the streaming consumer once; the
  perceived-latency win is baked in.
- **Ownership principle**: Zan takes the API-based / advanced work (streaming, extraction,
  LLM speed, lead schema). Miha takes the simpler frontend surface (PWA, screens, landing).
- **LLM real-latency lever**: TBD, Zan's track (distillation / model-tiering / warm-process
  / speculative extraction). Not blocking anything; picked later.

## Work split

### Miha — PWA + landing page (frontend)
- **PWA**: make `frontend/index.html` installable — `manifest.json`, service worker
  (offline app shell + cache the vendored CSS), add-to-home-screen, splash/icons.
- **App screens**: onboarding → dashboard (tiles from `/api/state` + total spend) →
  chat (typing indicator fires instantly) → needs card (renders `offer`: savings +
  `dontPayFor` + `why`) → "book" confirm.
- **Landing page**: marketing site for Frugl (the anti-upsell thesis, before/after,
  waitlist/CTA). Separate static page; can reuse the vendored styling.
- Works against a stubbed backend until Zan's endpoints land — the contract above is enough.

### Zan — API + LLM speed (backend)
- **Wire the 4 endpoints** in `main.py` (state/chat/profile/lead), integrating `llm.py`
  (chat + extraction) with the calculator (`compare()`), and append leads to `leads.jsonl`.
- **`/api/profile` is the money moment**: extraction → `compare()` → the anti-upsell card
  backed by real numbers.
- **LLM latency** (the advanced track — see options below).
- **Lead schema**: CP-compatible, written on `/api/lead`.

## Task checklists

### Miha (frontend — PWA, screens, landing)
Builds against the frozen contract; `/api/state` + `/api/profile` are live now, `/api/chat`
can be stubbed until Zan's stream lands.
- [ ] PWA plumbing: `manifest.json`, service worker (cache app shell + vendored CSS,
      offline fallback), app icons + splash, add-to-home-screen prompt.
- [ ] Dashboard: tiles from `/api/state`, total monthly spend, tap a tile → chat.
- [ ] Chat screen: consume the SSE token stream, typing indicator fires instantly.
- [ ] Needs card: render the `offer` object (savings, `dontPayFor`, `why` strings).
- [ ] Book confirm → `POST /api/lead` → done screen.
- [ ] Landing page: anti-upsell thesis, before/after, waitlist / CTA (static, reuses styling).

### Zan (backend — API, LLM, speed)
- [ ] `GET /api/state` — reshape demo-user into dashboard state. *(unblocks Miha)*
- [ ] `POST /api/profile` — real `compare()` + a canned profile first, then wired to extraction.
- [ ] `POST /api/chat` — SSE stream from `claude -p --output-format stream-json`.
- [ ] Profile extraction (highest risk): `claude -p` → `NeedsProfile` JSON, try/except → fallback profile.
- [ ] `POST /api/lead` — append to `leads.jsonl`, CP-compatible lead schema.
- [ ] LLM real-latency lever (advanced, TBD).

## LLM latency track (Zan) — candidate approaches
Real latency today is 9-29s with big grounding context. Angles, roughly by bang-for-buck:

1. **Streaming** (`--output-format stream-json`) → SSE/chunked to the client. Tokens appear
   in ~1-2s; kills *perceived* latency. Biggest single win.
2. **Context distillation** — inject a compact per-vertical grounding brief, not the raw
   slice. Fewer input tokens = faster real latency + cheaper. ("distilled advisor-brief" idea.)
3. **Model tiering** — faster model for chat turns, keep the strong model only for the
   accuracy-critical profile extraction.
4. **Warm process / session reuse** instead of a cold subprocess per call.
5. **Speculative extraction** — build the profile in the background as the chat progresses,
   so the "see my offer" tap returns instantly.

## Deferred
Voice (phase-2, `docs/voice-roadmap.md`).
