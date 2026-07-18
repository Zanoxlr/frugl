# Key signals per vertical — research foundation

Deep research (2026-07) into which user signals actually determine the right-fit
recommendation per vertical, grounded in (a) our real dataset, (b) what `compare()`
keys on today, and (c) the live Slovenian market. This defines the `signals` schema.

## The headline finding
The engine today reads **four** signals total, out of ~20 the old schema declared:

| Vertical | Signals the calculator actually uses now |
|---|---|
| telco | `dataNeedGB`, `watchesSport` |
| energy | `annualKwh` (+ a hidden ET-vs-VT rate assumption) |
| insurance | `paysLegacyDopolnilno` |

Everything else in `needs_profile.schema.json` is declared but dead. So the schema
over-promises and the calculator is much narrower than it looks. The research below
tiers every candidate signal into **live now / high-value next (data already supports) /
aspirational (needs new data)** so we only extract what changes an answer.

## Cross-vertical model: where each signal lives
Three homes, decided by *what the signal is*, not which vertical asked it:

1. **Line-derived** — read off the user's current subscriptions, never asked. The most
   reliable signals, because a statement line beats a user's belief. e.g. legacy
   dopolnilno presence, car AO presence, current plan specs (dataGB, unit rate).
2. **Household facts** (shared block, asked once, imported by any vertical): `city`,
   `hasCar`, `carFinancing`, `homeOwnership` (owner/tenant), `lineCount`,
   `dependentsAndDebt`, `hasPet`.
3. **Per-vertical signals** — vertical-specific facts + true preferences (below).

This is why the shared-household decision was right: `carFinancing` and `homeOwnership`
are asked once and drive **insurance** rules; `lineCount` is asked once and multiplies
**telco** savings.

## Resolved: `paysLegacyDopolnilno` → derive from a line, don't ask
The open question is settled by the research: **derive it** from a current line of
`kind: "legacy_dopolnilno"`, drop the preference gate. Reasons:
- The product was abolished 31 Dec 2023 and policies auto-terminated ([gov.si](https://www.gov.si/novice/2023-12-29-z-novim-letom-prihaja-obvezni-zdravstveni-prispevek)),
  so there is no valid state where a user "prefers" to keep paying it — the line's mere
  presence *is* the finding.
- Users are confused about exactly this (the demo's whole point): asked "do you pay
  dopolnilno?" they answer about the state OZP, not the stale private line.
- Today the drop is double-gated (`kind == legacy_dopolnilno` AND the pref), so if
  extraction forgets the pref, the **biggest reveal silently doesn't fire**. Deriving
  removes that fragility. `car_ao` is already handled this way.
- Post-2024 Vzajemna sells discretionary health under other names ("Specialisti"), so
  the name-based classifier is safe; if a start-date is ever available, `>= 2024-01-01`
  is a secondary check.
Keep `paysLegacyDopolnilno` only as an optional UI confirmation ("we think this is the
abolished product — confirm before cancelling"), never as the gate.

---

## Telco
Ranked by decision impact:

| signal | type | determines | data supports | extraction |
|---|---|---|---|---|
| `dataNeedGB` | enum/number | cheapest mobile plan whose full-speed GB clears the threshold — the biggest euro lever | **yes** (LIVE) | easy |
| `lineCount` | number | multiplies every mobile saving across household SIMs | partial (engine ignores it) | easy |
| `paidTvPacksUsed` | enum[] `sport/movies/kids/balkan/adult/none` | which discretionary TV packs to keep vs drop (generalizes `watchesSport`) | yes (sport LIVE, rest in data) | easy |
| `wantsFixedBroadband` | bool | keep/drop/rightsize the fixed+TV bundle (usually the biggest line) | partial (fixPackages loaded, unused) | med |
| `openToSwitchOperator` | bool | MVNO jump vs same-operator downsize (governs realism) | yes (`noContract` per plan) | med |
| `travelsOutsideEU` | bool | blocks roaming-disabled tiers (e.g. bob rdeci) | partial (add-on notes only) | easy |
| `budgetPriority` | bool | tie-break cheapest-wins vs keep-what-works | n/a | easy |

- **Live now**: `dataNeedGB` (drives ~216 EUR/yr on Marko), `watchesSport` (drops sport add-ons).
- **High-value next (data supports)**: `lineCount` (SI ~130% mobile penetration → multi-SIM is normal, [DataReportal 2025](https://datareportal.com/reports/digital-2025-slovenia)); generalize `watchesSport`→`paidTvPacksUsed` (HBO/CineStar/Pink/Balkan/VOYO prices all in `tvAddons`); rightsize the fixed+TV bundle via `wantsFixedBroadband`; `openToSwitchOperator` gated on `noContract`.
- **Aspirational**: precise metered usage (needs bill parsing); family/3play discount deltas (need a per-line discount table); non-EU/intl calling (need a roaming/tariff table); address-level FTTH-vs-DSL availability (need an AKOS coverage lookup).

**Recommended `signals` (telco):**
```json
{ "dataNeedGB": "mid", "lineCount": 2, "watchesSport": false,
  "paidTvPacksUsed": ["movies"], "wantsFixedBroadband": true,
  "openToSwitchOperator": true, "travelsOutsideEU": false, "budgetPriority": true }
```
Drop from old schema: `wantsSpecialChannels` (→ typed `paidTvPacksUsed`), `worksFromHome`
(weak proxy, never used); rename `phoneCount` → `lineCount`.

---

## Energy
Ranked by decision impact:

| signal | type | determines | data supports | extraction |
|---|---|---|---|---|
| `annualKwh` | number | master input: bill size AND the fixed-fee-vs-unit-price break-even | **yes** (LIVE) | med (on the bill) |
| `meterType` | enum `single_ET`/`dual_VT_MT` | which rate we rank on; wrong pick misranks every plan | partial (data has all three; calc only ET-else-VT) | easy |
| `hasGas` | bool | whether to compare gas + steer to a dual-fuel bundle | yes | easy |
| `dayNightSplit` | enum `mostly_day/even/mostly_night` | weights VT vs MT; dual-tariff pays at ~30%+ night | partial (rates exist, never blended) | hard |
| `priceCertaintyPref` | enum `cheapest_now/price_locked` | variable vs fixed-price promo | yes (`isFixed`) | easy |
| `contractLockTolerance` | enum `no_lock/ok_12mo` | eligibility of 12-mo promos | yes (`commitmentMonths`) | easy |
| `annualGasKwh` | number | gas bill size + gas fee-vs-unit break-even | yes | med |
| `eInvoiceOk` | bool | e-racun ~halves the fixed fee — decisive for low usage | partial (prose only) | easy |

- **Live now**: `annualKwh` — `None` → return the lowest-unit vs zero-fee **trade-off** (no quoted saving); a number → rank by `annualKwh*unitRate + 12*fixedFee`. The break-even is real: Energetika Ljubljana (ET 0.11389, **0** fee) beats GEN-I (ET 0.1089, 2.43 fee) below **~5,850 kWh/yr**; a typical LJ flat (~2.5–3.5k) sits under it, an all-electric house (~5–7k) crosses over.
- **High-value next (data supports)**: `meterType` (stop assuming ET; blend VT/MT for dual) — highest-leverage fix; `hasGas`+`annualGasKwh` (turn on gas + dual-fuel nudge); `priceCertaintyPref`+`contractLockTolerance` (filter before ranking, using existing `isFixed`/`commitmentMonths`).
- **Aspirational**: `eInvoiceOk` as a real discount (need e-invoice fee as a field); `greenPreference` (need a clean `isGreen` flag); `bookedPowerKw` (omreznina lever since the [Oct-2024 reform](https://www.varcevanje-energije.si/distribucija-in-cena-elektrike/omreznina-za-prikljucno-moc-obracun-elektrike-po-novem/) — supplier-independent, belongs in a "lower your booked power" tip, not the ranking); EV/heat-pump/solar + time-of-use tariffs (none in corpus).

**Recommended `signals` (energy):**
```json
{ "annualKwh": null, "meterType": null, "hasGas": null, "annualGasKwh": null,
  "dayNightSplit": null, "priceCertaintyPref": null, "contractLockTolerance": null,
  "eInvoiceOk": null, "currentSupplier": null, "currentElectricityRateEurPerKwh": null }
```
`currentElectricityRateEurPerKwh` (off the bill) is what would let us quote a real saving
instead of `null`. Green/heating/EV/bookedPower are collected-but-not-scored (aspirational).

---

## Insurance
Value is keep-vs-drop, not switch (our data has ranges, no exact premiums). Ranked:

| signal | type | determines (keep/drop) | data supports | extraction |
|---|---|---|---|---|
| legacy dopolnilno (line) | derived bool | **always DROP** — abolished 2024, double-pays on top of OZP; biggest reveal (420/yr) | **yes** (LIVE) | easy (derive) |
| `carFinancing` | enum `owned_outright/leased/financed/none` | GAP: keep if leased/financed, **DROP if owned** | partial (whoNeedsIt) | easy |
| `homeOwnership` | enum `owner/tenant/none` | tenant must NOT insure the structure → drop structure cover | partial | easy |
| `valuesFasterPrivateAccess` | bool | discretionary health riders: keep only if they value queue-jumping (OZP funds the treatment itself) | yes (`notCoveredGap`) | med |
| `dependentsAndDebt` | obj | life cover: keep if breadwinner/mortgage, question if single+no-debt (esp. fund-linked) | partial | easy |
| `expectsDentalWork` | bool | dental rider: keep if concrete work, else over-sold (white fillings free for all from 1 Jul 2026) | yes | med |
| `carValueTier` | enum `low/mid/high` | full kasko justified on newer/financed cars, drop on old cheap car | partial | easy |
| `floodExposed` | bool/null | flood rider: keep if exposed, drop only if verifiably not | partial (no zone map) | hard |
| `coverElsewhere` | obj `{personalAccident, roadsideAssist}` | drop duplicate accident/assistance lines already covered by kasko/AMZS/credit card | partial | med |
| `travelFrequency` | enum `rare/occasional/frequent` | annual travel policy is an over-buy for one holiday/yr | partial | easy |

- **Live now**: legacy-dopolnilno drop (`INS_LEGACY_DOPOLNILNO`, attaches OZP 39.36); `car_ao` classified so AO is never dropped.
- **High-value next (data supports the reasoning)**: `carFinancing`→GAP-on-owned drop; `homeOwnership`→tenant-structure drop; `valuesFasterPrivateAccess`+`expectsDentalWork`→drop unneeded health riders (grounded in `publicCoverBaseline.notCoveredGap`, the honest OZP boundary); `coverElsewhere`→duplicate-cover drops.
- **Aspirational**: real flood answer (need postcode→flood-zone lookup, e.g. ARSO/Atlas okolja); life adequacy in euros (need income/debt/dependents math); full-kasko break-even (need car value + premium); earthquake sizing (need sum insured + co-share); bonus-malus/real AO premium (out of scope per the premium caveat — AO stays "keep, mandatory").
- **Off-thesis note**: earthquake (potresno) is SI's most under-insured risk → almost always **keep**; since Frugl is anti-upsell we don't actively push buying it, at most flag the gap gently.

**Recommended `signals` (insurance):**
```json
{ "homeOwnership": null, "carFinancing": null, "carValueTier": null,
  "dependentsAndDebt": { "hasDependents": null, "hasMortgageOrLoan": null },
  "healthPrefs": { "valuesFasterPrivateAccess": null, "expectsDentalWork": null },
  "floodExposed": null, "travelFrequency": null,
  "coverElsewhere": { "personalAccident": null, "roadsideAssist": null } }
```
Excluded: any premium/sum-insured field (we have none); `earthquakePresent` (keep-by-default,
off-thesis); mandatory `car_ao` (derived from the line, never asked). Note `carFinancing`
and `homeOwnership` live in the shared **household** block, not here — imported by the engine.

---

## What this implies for the build
- **Schema scope**: the "high-value next" signals are cheap and use data we already hold —
  they roughly 3–5x the reveals per vertical (multi-SIM telco, generalized TV packs,
  meter-type-correct energy ranking, GAP/tenant/health-rider insurance drops). Worth
  building the rules, not just collecting the fields.
- **Mark aspirational fields collected-but-not-scored** so the advisor can chat about them
  without the calculator ever implying a euro impact it can't compute.
- **Extraction target stays lean**: line-derived facts aren't asked, household facts are
  asked once, per-vertical signals are the short lists above.
