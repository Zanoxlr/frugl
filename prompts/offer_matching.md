# Offer Matching — Rule-Based (no second LLM)

> Canonical model now lives in [../docs/signals-research.md](../docs/signals-research.md),
> `preferences.schema.json`, and `profile.schema.json`. Since that refactor: household facts
> (carFinancing, homeOwnership, lineCount) moved to the shared UserState; the legacy-dopolnilno
> drop is DERIVED from a subscription line of kind `legacy_dopolnilno` (no `paysLegacyDopolnilno`
> preference); the sport-only TV rule generalized to `paidTvPacksUsed`. The rule *logic* below
> still holds; treat the schema files as the source of truth for field names.


Input: a `NeedsProfile` (needs_profile.schema.json) + the `{{VERTICAL_DATA}}` slice + `{{USER_CURRENT_SUBS}}`.
Output (consumed by the advisor LLM, or by app code): a `recommendation` (a real item from DATA, or null) + a concrete `dontPayFor[]` list. Every entry MUST reference a real field/id in DATA. If nothing in DATA fits, output `recommendation: null` + reason. Never invent an item.

These are the same deterministic rules the code engine (`backend/compare.py`) applies. Field names below match the REAL data files, not an idealized shape.

## Shared rules (all verticals)
- R0. Only recommend items present in DATA. If a needed capability is missing, return null + "tega ni v podatkih."
- R1. Never recommend a higher tier than the lowest one that satisfies the stated need.
- R2. `currentMonthlyEur` for each vertical is ALWAYS the pass-through sum of the user's current line prices. Never recompute it from unit prices (energy's all-in bill will not reconcile from ex-VAT unit rates).
- R3. `annualSavingsEur` is null whenever `monthlySavingsEur` is null. Never emit 0 to mean "unknown".

## Telco
Mobile plans live in TWO files: `telco/mobile_packages.json` (premium operators: Telemach id 1, Telekom id 2, A1 id 3, T2 id 4) and `telco/telco_mvno.json` (MVNOs HOT + BOB, the fresh scrape with full-speed detail). The engine uses the MVNO file for HOT/BOB and drops the stale HOT/BOB rows in `mobile_packages.json` to avoid duplicates.

- Mobile plan fields: `mobile_packages.json` → `group` (name), `priceEur`, `dataGB`, `unlimited` (int 0/1 → bool), `operator`. `telco_mvno.json` → `providers[].plans[]` with `name`, `monthlyEur`, `dataGB`, `unlimited`.
- **fullSpeedGB** (the GB served at full speed before throttle) is what the need is matched against, NOT nominal "unlimited":
  - premium/`mobile_packages`: `fullSpeedGB = dataGB` when set, else `inf` for uncapped unlimited plans. (Do NOT parse the HTML description for GB — the number there is EU-roaming GB.)
  - MVNO/`telco_mvno`: `fullSpeedGB = dataGB` when set; else parse the "(N GB at full ...)" phrase in `keyFeatures`; else `inf`.
- TV add-ons: `telco/tv_schemes.json` rows with `isAddon: 1` and a non-null `addonPriceEur` (e.g. A1 "Arena Sport Premium" id 24, `addonPriceEur` 4.99). `telco/addon_tier_free_paid.json` `paidPriceEur: 0.00` means "bundled-free in that tier" — it is NOT the standalone price; ignore it for pricing.
- Fixed internet+TV packages: `telco/retail_prices.json` `operators[].packages[]` (`name`, `monthlyEur`).

Rules:
1. **Unused paid TV add-on.** If `telco.watchesSport == false` (or null) and a current line matches a sport TV add-on (`Arena`, `Sport`) with price > 0 → `dontPayFor` with its name + monthlyEur. Rule code `TELCO_UNUSED_SPORT_ADDON`.
2. **Right-size mobile.** Threshold = `dataThreshold(telco.dataNeedGB)` (`low`→5, `mid`→20, `high`→100, `unlimited`→inf, or a number). Among ALL operators, pick the cheapest plan with `fullSpeedGB >= threshold` and `priceEur > 0`; tie-break `priceEur` then operator name. Recommend the swap ONLY if it is cheaper than the current mobile line. Rule code `TELCO_MOBILE_RIGHTSIZE`.
3. **Keep fixed broadband** as-is unless a cheaper package meets the same need; the persona keeps it.
4. Never assume a bundle is cheaper without a DATA price.

## Energy (electricity + gas)
Fields per `data/energy.json` `providers[].plans[]`: `energyEurPerKwh` (electricity → dict `{VT, MT, ET}`; gas → a single number), `energyEurPerM3` (null in this dataset), `fixedMonthlyEur` (can be 0, e.g. Energetika Ljubljana, or null), `greenOrFixed` (string; "fixed" substring ⇒ fixed-price tariff), `utility` (`electricity`|`gas`). Regulated network charges + levies + VAT (`regulatedComponents`) are supplier-independent and are the same whichever supplier wins, so they are NOT part of the comparison.

- Unit rate for ranking electricity = `ET` if present, else `VT` (state the single-tariff assumption). Gas unit rate = the number directly.
1. **No usage → trade-off, no savings.** If `energy.annualKwh` is null, do NOT crown one winner (cheapest unit price is wrong when fixed fees differ — a zero-fixed-fee supplier beats a lower-unit one below a break-even usage). Return a trade-off: the lowest-unit-price plan AND the lowest-fixed-fee plan, `monthlySavingsEur: null`, `annualSavingsEur: null`, plus an assumption note. Rule code `ENERGY_NO_USAGE_TRADEOFF`.
2. **Usage known →** rank candidates by `annualKwh × unitRate + 12 × fixedFee` and name the cheapest; still report savings as null here because the current line is an all-in bill that cannot be decomposed into an energy-only figure from this dataset.
3. **Dual fuel** only if `energy.dualFuel == true`. Green filtering is dropped (no `isGreen` flag exists in the data). Null-guard every `min()` (some `fixedMonthlyEur` are null).

## Insurance
Fields per `data/insurance.json` `providers[].products[]`: `name`, `type` (`car`|`home`|`health`|`life`), `typicalMonthlyEurRange` / `typicalAnnualEurRange` (RANGES only — there are NO exact premiums; add-on `extraEur` is null throughout). `publicCoverBaseline.ozp.currentMonthlyEur` = 39.36 (state OZP since Mar 2026) is the narrative baseline.

- Because no exact premium exists, `recommendation.monthlyEur` is null and the value is entirely in `dontPayFor`. A `dontPayFor` entry's amount falls back to the CURRENT line's own `monthlyEur` (since `extraEur` is null).
1. **Legacy dopolnilno (top reveal).** If `insurance.paysLegacyDopolnilno == true` and a current line is a "dopolnilno zdravstveno" product → `dontPayFor` with its monthlyEur. Rule code `INS_LEGACY_DOPOLNILNO`. Why: since 2024 the compulsory OZP replaced it; paying a private line on top is likely double-paying.
2. **GAP / kasko add-ons** only relevant if `carFinanced == true`; drop otherwise.
3. **Home/building** only if `ownsHome == true`; a tenant (`isTenant == true`) does not insure the structure.
4. Mandatory car AO (`hasCar == true`) is kept — it is a "leave it alone" line, not a saving.

## Output shape (per vertical)
```
vertical: telco|energy|insurance
currentMonthlyEur: <pass-through sum, number>
recommendation: <object or null>
recommendedMonthlyEur: <number or null>
dontPayFor: [ { name, monthlyEur, ruleCode, why? } ]
monthlySavingsEur: <number or null>
annualSavingsEur: <number or null>   # null iff monthlySavingsEur is null
notes: [ <assumption strings, no sumniki> ]
```
`why` strings are added only in B2 (`?explain=true`), by `backend/reasons.py`, keyed to `ruleCode`. B1 (`?explain=false`) returns identical numbers with no `why`. All Slovenian text is written without sumniki (c/s/z, never č/š/ž).
