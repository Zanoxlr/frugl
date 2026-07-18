# cp-advisor — seed dataset

Grounding corpus + demo persona for the B2C multi-utility subscription advisor POC (Slovenian market).
The advisor reads a consumer's current subscriptions across telco, energy, insurance and water, then
gives **anti-upsell** advice: cut dead spend, right-size over-provisioned plans, catch redundant/legacy
charges, and leave alone what shouldn't change.

## Public-safety verification (commission check)

**Requirement:** the telco data must contain **NO commission fields** (this is customer-facing advice;
seller economics must never leak into it).

**What was checked:** every telco JSON in `telco/` was grepped case-insensitively for `commission`,
`CommissionAmount`, and the Slovenian equivalents `provizij(a)`, plus `kickback`, `margin`, `payout`, `reward`.

**Result: CLEAN.** No commission-type keys were found in any telco file — not in the original exports and
not in the copies here. The exports were built to exclude commission, and this verifies it rather than
assuming it. Nothing had to be stripped or re-saved.

Full list of keys present in the telco set (for transparency):
- `operators.json`: id, title, slug, mobileHas5G, mobileMaxDown, mobileMaxUp, smartTvCost, additionalTvCost
- `tv_schemes.json`: id, name, operatorId, level, channelCount, channels, isAddon, addonPriceEur, parentSchemeId
- `fix_packages.json`: id, operator, operatorId, tier, level, baseTvSchemeId, tvChannelCount, includedTVs, includedSmartTVs, includedMobileCount, timeShiftDays, description
- `mobile_packages.json`: id, operator, operatorId, group, level, dataGB, unlimited, callMinutesSlo, sms, euRoamingGB, priceEur, noContract, description
- `addons.json`: id, operator, operatorId, name, category, channelSchemeId, phase1Months, phase1PriceEur, phase2PriceEur, avgMonthlyEur, discountText, description
- `addon_tier_free_paid.json`: operator, tier, addon, addonCategory, includedFree, paidPriceEur

Note: the `margin`/`bonus`/`payout` matches that DO exist are all in `insurance.json` and are legitimate
insurance-domain terms (bonus-malus class, claim payouts, first-loss limits), not sales commissions.

## Files

### `telco/` — grounding corpus (REAL, from prod DB)
Source: CalculatorPlatform production export. These describe the four premium Slovenian operators
(Telemach, Telekom Slovenije, A1, T2) plus the two discount MVNOs.

| File | Contents | Real/Mock |
|------|----------|-----------|
| `operators.json` | 7 operators (4 premium + HOT + BOB + an energy pseudo-operator), network specs, TV costs | REAL (prod DB) |
| `tv_schemes.json` | TV channel schemes and paid channel-package add-ons (HBO, Arena Sport Premium, Pink, …) with prices | REAL (prod DB) |
| `fix_packages.json` | Fixed broadband + TV bundle tiers per operator | REAL (prod DB) |
| `mobile_packages.json` | Mobile plans per operator (data, minutes, price) | REAL (prod DB) |
| `addons.json` | Streaming/TV/service add-ons with phase-1/phase-2 pricing | REAL (prod DB) |
| `addon_tier_free_paid.json` | Which add-on is free vs paid per package tier | REAL (prod DB) |
| `telco_mvno.json` | HOT (Hofer Telekom) and BOB discount MVNO plans — folded into the telco set per task | REAL (scraped 2026-07-18 from hot.si / bob.si) |

### Verticals (REAL, scraped 2026-07-18)
| File | Contents | Real/Mock |
|------|----------|-----------|
| `energy.json` | 6 electricity+gas suppliers (GEN-I, Petrol, Energija plus, Elektro energija, Energetika Ljubljana, ECE), standard vs fixed/promo tariffs, per-kWh + fixed fees. Note: no active price cap as of 2026. | REAL (scraped) |
| `insurance.json` | Triglav, Sava, Generali, Vzajemna + smaller insurers; car (AO/kasko), home, health lines. Carries the **critical marketNote**: dopolnilno zdravstveno zavarovanje was abolished 31 Dec 2023 and replaced by the compulsory state OZP (~37.17 EUR/mo from March 2025). Premiums are illustrative ranges, not quotes. | REAL structure (scraped); premiums = market-typical ranges |
| `water.json` | Municipal water utilities (VOKA Snaga Ljubljana, Mariborski vodovod + Nigrad). `isCompetitive: false`, `canSwitchProvider: false` — info-only vertical, no switch. | REAL (scraped) |

### `demo_user.json` — demo persona (MOCK)
"Marko Novak, 34, Ljubljana." A realistic set-and-forget consumer with current subscriptions across all
four verticals, **rigged so the advisor's anti-upsell reveals land**. Total spend **~198.78 EUR/mo**
(~2,385 EUR/yr). All provider/plan names, tiers and unit prices reference the real grounding corpus in
this folder; the `monthlyEur` bundle/bill figures without a public monthly price are illustrative and
flagged inline (`grounding` field on each entry).

The three primary rigged "gotcha" subscriptions:
1. **Unused sport add-on** — A1 Arena Sport Premium, 4.99/mo, never watches sport (grounded to `tv_schemes.json`, real 4.99 price). Cancel outright.
2. **Over-provisioned mobile** — A1 MaksiMIO 500 GB, 27.99/mo, actual use ~12-15 GB. Right-size to MidiMIO (20.98) or an MVNO (~6-10).
3. **Redundant/legacy insurance** — Vzajemna dopolnilno zdravstveno zavarovanje, 35/mo, a product ABOLISHED in 2024 and replaced by the compulsory state OZP. Biggest single reveal (~420 EUR/yr).

Plus one soft nudge (energy on a standard tariff when a cheaper same-supplier promo exists) and two
correctly-left-alone lines (municipal water = info-only; Triglav car AO = mandatory, keep).

## Validation
All JSON files validated with `python3 -m json.tool` / `json.load`. See the commission section above for
the public-safety result.
