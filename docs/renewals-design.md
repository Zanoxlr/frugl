# Renewals — contract lifecycle + "we found you a better option"

The feature: each subscription shows **how long it's still active**, and about a month before
it ends Frugl looks up a newly-available alternative and offers it. This doc is the frozen
backend contract Miha builds the frontend against.

The clever bit: the "lookup of a newly available one" is **not new logic**. It's the existing
`compare()` engine, which already turns a subscription into a right-fit alternative from the
scraped offer corpus. Renewals only add a **lifecycle layer** on top: knowing when a line ends
and flipping into "renewal mode" at the right time. The offer object is byte-for-byte the same
shape already rendered on the needs card, so the renewals screen reuses that rendering.

---

## 1. Data model — `contract` per line

Every subscription in `data/demo_user.json` now carries a `lineId` (stable id) and a `contract`
block. `contract: null` means no lock (switch anytime). SI contract reality maps to four shapes:

| Line type | Reality | `contract` |
|---|---|---|
| Telco fiber/TV (vezava) | 24-mo lock, then auto-renews, 30-day notice | `{startDate, termMonths:24, endDate, noticePeriodDays:30, autoRenews:true}` |
| Telco mobile | 24-mo lock | same shape, `termMonths:24` |
| Energy variable (redni) | no lock, switch anytime | `null` |
| Energy fixed promo (akcijski) | 12-mo lock | `{termMonths:12, endDate, noticePeriodDays:30}` |
| Car insurance | annual, auto-renews unless cancelled | `{termMonths:12, endDate, noticePeriodDays:30, autoRenews:true}` |
| Water / add-ons / statutory health | no contract | `null` |

`endDate` is stored for clarity but is derivable from `startDate + termMonths`.

---

## 2. Derived `lifecycle` — what the frontend renders

`backend/lifecycle.py` computes this from `contract` + a `today`. **The frontend never computes
dates**, it reads `status` and renders. Four statuses:

- **`no_contract`** — no lock. Badge: "zamenljivo kadarkoli". No countdown. (variable energy, water, add-ons, health)
- **`active`** — locked, more than a window away. Muted: "aktivno do DD.MM.YYYY".
- **`renewal_window`** — inside the window (see below). Highlighted, and this is where the offer attaches.
- **`expired`** — past the end date.

The renewal window opens far enough ahead of the cancellation-notice deadline to leave runway:
`window = max(30, noticePeriodDays + 14)`. So a 30-day-notice contract starts offering at **44
days out**, leaving ~14 days to actually cancel before it auto-renews.

Each `lifecycle` block:

```jsonc
{
  "status": "renewal_window",
  "endDate": "2026-09-01",
  "daysRemaining": 40,
  "noticeDeadline": "2026-08-02",     // endDate - noticePeriodDays: last day to cancel
  "daysToNoticeDeadline": 10,         // frontend can turn this red when it gets small
  "actionRequired": true,
  "autoRenews": true
}
```

Use `daysToNoticeDeadline` + `autoRenews` to show the auto-renew trap ("odpovej do 2.8. ali se
samodejno podaljša"). `lifecycle` never raises: any unparseable contract degrades to `no_contract`,
so a bad date can't 500 the dashboard.

---

## 3. Endpoints (the contract Miha builds against)

> Status: `lifecycle.py` + contract data + tests are **built and green**. The two endpoint
> wirings below live in `main.py` and are **deferred** until the current backend session lands,
> to avoid a merge conflict. The shapes here are frozen — Miha can build against them now with a
> stub.

### `GET /api/state` — gains `contract` + `lifecycle` per line

Everything it returns today, plus, on each line in `currentSubscriptions`:

```jsonc
{
  "lineId": "telco-fixed-a1-xplore",
  "vertical": "telco", "provider": "A1", "planName": "A1 Xplore TV maxi+",
  "monthlyEur": 55.99,
  "contract": { "startDate": "2024-09-01", "termMonths": 24,
                "endDate": "2026-09-01", "noticePeriodDays": 30, "autoRenews": true },
  "lifecycle": { "status": "renewal_window", "endDate": "2026-09-01",
                 "daysRemaining": 40, "noticeDeadline": "2026-08-02",
                 "daysToNoticeDeadline": 10, "actionRequired": true, "autoRenews": true }
}
```

This alone powers "active until X" badges on every card.

### `GET /api/renewals` — the "expiring + better offer found" feed

For a dedicated renewals screen or a home banner. Optional `?asOf=YYYY-MM-DD` to pin the date.

```jsonc
{
  "asOf": "2026-07-23",
  "renewals": [{
    "lineId": "telco-fixed-a1-xplore",
    "vertical": "telco",
    "current": { "provider": "A1", "planName": "A1 Xplore TV maxi+", "monthlyEur": 55.99 },
    "lifecycle": { "status": "renewal_window", "daysRemaining": 40, "noticeDeadline": "2026-08-02" },
    "offer": { /* exact compare() result: recommendation, recommendedMonthlyEur,
                  monthlySavingsEur, annualSavingsEur, dontPayFor[], notes[] */ }
  }]
}
```

`offer` is the same object the needs card already renders — no new render logic, just a new list.

---

## 4. Sync (demo) vs scheduled (real product)

- **Demo (what we ship):** the frontend reads `/api/state` + `/api/renewals` and renders live.
  No background job. This is all the hackathon needs.
- **Real product (design only, not built):** a daily cron runs the same `lifecycle` scan per
  user and fires a push/email at the window. `lifecycle.due_for_renewal()` is already the scan
  primitive. Not wired for the POC (one demo user, no notification infra in this repo).

---

## 5. The "today" problem (demo stability)

The persona is static but contracts are date-based, so a hardcoded `endDate` drifts. `lifecycle`
resolves today as: explicit `as_of` arg → `FRUGL_DEMO_TODAY` env → real `date.today()`. For a
stable stage demo, **pin `FRUGL_DEMO_TODAY=2026-07-23`** (or pass `?asOf=2026-07-23`). On that
date exactly one line — the telco fiber — sits in its renewal window (40 days out, 10 days to
cancel), which is the demo renewal beat: "your fiber contract ends soon, here's a better package."
All other lines are `active` or `no_contract`. This is asserted by `tests/test_lifecycle.py`.

---

## 6. Status

Built + green (`python3 -m pytest tests/test_lifecycle.py`, 17 tests):
- `data/demo_user.json` — `lineId` + `contract` on all 7 lines
- `backend/lifecycle.py` — pure lifecycle fn, `annotate_subscriptions()`, `due_for_renewal()`
- `tests/test_lifecycle.py`

Deferred (coordinate with the backend session, `main.py`):
- wire `lifecycle` into `/api/state`
- add `GET /api/renewals` (attach `compare()` offer per due line)
