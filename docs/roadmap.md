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
| `GET /api/state` | – | `{ persona, currentSubscriptions[], totals:{monthlyEur, byVertical} }` |
| `POST /api/chat` | `{ vertical, history:[{role,text}] }` | `{ reply }` (later: streamed) |
| `POST /api/profile` | `{ vertical, history }` | `{ profile:<NeedsProfile>, offer:<compare() result> }` |
| `POST /api/lead` | `{ vertical, history }` | `{ ok, leadId }` |

`offer` = the exact `compare()` result already shipped: `{ currentMonthlyEur,
recommendation, recommendedMonthlyEur, dontPayFor[], monthlySavingsEur,
annualSavingsEur, notes[] }`, with B2 `why` strings when `?explain=true`.

Contract rule: the backend owns these shapes; the frontend renders them. Any field
change goes here in the same PR, so neither side breaks silently.

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
Voice (phase-2, `docs/voice-roadmap.md`). Stale "SubSmart" naming cleanup (README is canonical Frugl).
