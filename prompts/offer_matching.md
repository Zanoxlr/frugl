# Offer Matching — Rule-Based (no second LLM)

Input: a `NeedsProfile` (needs_profile.schema.json) + the `{{VERTICAL_DATA}}` slice + `{{USER_CURRENT_SUBS}}`.
Output (consumed by the advisor LLM, or by app code): a `recommendation` (a real item from DATA) + a concrete `dontPayFor[]` list. Every recommendation and every dontPayFor entry MUST reference a real field/id in DATA. If nothing in DATA fits, output `recommendation: null` + reason. Never invent an item.

These are deterministic rules. Run them in order, per vertical.

## Shared rules (all verticals)
- R0. Only recommend items present in DATA. If a needed capability is not in DATA, return null + "tega ni v podatkih."
- R1. Never recommend a higher tier than the lowest tier that satisfies the stated need.
- R2. If the user's CURRENT sub already satisfies the profile and costs <= the best matching offer, recommend "stay" (no switch). Say it plainly.
- R3. Any DATA item with `isAddon: true` and `addonPrice > 0` that the profile does not require -> goes to `dontPayFor` with its name + addonPrice.

## Telco
Fields: operators[].tvSchemes[].channels[] (each channel has name, isAddon, addonPrice), packages[] (tier, monthlyPrice, includedDataGB, ...), mobilePlans[] (dataGB, price), addOns[].

1. Sport: if `telco.watchesSport == false` (or null) -> every channel/scheme with `isAddon:true` that is sport (e.g. sport pack, "Sport TV", "Arena") and `addonPrice > 0` goes to `dontPayFor` as "sportni dodatek {name} {addonPrice}/mes - ne gledas sporta."
2. Package tier: pick the LOWEST `packages[]` tier whose `includedDataGB` / speed meets `dataNeedGB`. Do not upsell "Premium" if "Basic"/"Standard" covers it.
3. Multi-phone: if `telco.phoneCount >= 2` and DATA has a family/bundle package -> prefer it over N single mobilePlans ONLY if its total price (from DATA) is lower; otherwise recommend N × cheapest matching single plan. Never assume a bundle is cheaper without the DATA number.
4. Data need: match `mobilePlans[]` to `dataNeedGB`. If user is 'low' data, flag any current "unlimited"/high-GB plan the user pays for as `dontPayFor` ("placujes neomejene podatke, porabis malo").
5. Work from home: only if `worksFromHome == true` recommend fixed broadband / higher speed. If false, drop it from the recommendation.
6. Paid channels the user does not name in `wantsSpecialChannels` but pays for now -> `dontPayFor` with name + addonPrice.

## Energy (electricity + gas)
Fields: suppliers[].tariffs[] (pricePerKwh, fixedFee, isGreen, isFixedPrice, fuel: electricity|gas).

1. NEVER output a fabricated monthly total. If `energy.annualKwh` is null -> recommendation compares on `pricePerKwh` + `fixedFee` only, and the advisor explains: strosek = poraba × cena/kWh + fiksna taksa.
2. If `annualKwh` known -> compute annual = annualKwh × pricePerKwh + 12 × fixedFee for each candidate tariff and rank; show the input numbers used (grounded, since inputs come from DATA + user).
3. Dual fuel: if `dualFuel == true`, prefer a supplier offering both electricity + gas in DATA (bundle) only if combined price beats best separate pair from DATA; else recommend cheapest per fuel separately.
4. Green: if `greenPreference == true` filter to `isGreen: true` tariffs, then apply price ranking. If false, do NOT restrict to green (green often costs more) and if the current plan is a premium green one they did not ask for -> `dontPayFor` ("placujes zeleni tarif, nisi rekel da ti je pomembno").
5. Fixed vs market: if `wantsFixedPrice == true` prefer `isFixedPrice:true`; if false, do not push a fixed tariff (usually pricier as a hedge they did not ask for).
6. If current supplier's `pricePerKwh` + `fixedFee` is within noise of the best DATA offer -> recommend stay (switching energy for cents is not worth it).

## Insurance
Fields: insurers[].products[] (name, premium, riders[] where each rider has name, price, and is the upsell), plus the 2024 dopolnilno->OZP change.

1. GAP: if `insurance.carFinanced == false` (or no car) and DATA has a GAP rider on the auto product -> `dontPayFor`: "GAP kritje {price} - avto ni na leasing, GAP nima smisla."
2. Legacy health: if `paysLegacyDopolnilno == true` -> `dontPayFor`: "dopolnilno zdravstveno - od 2024 ga je zamenjal obvezni OZP, ce ga placujes se loceno je odvec." (High-priority flag.)
3. No car: if `hasCar == false`, any auto product / auto riders in current subs -> `dontPayFor`.
4. Home: recommend home/property product ONLY if `ownsHome == true`. If `isTenant == true`, do NOT recommend building insurance; at most contents ("zavarovanje opreme"), and flag any building/structure cover in current subs as `dontPayFor` ("kot najemnik ne zavarujes zgradbe, to je lastnikovo").
5. Riders in general: every `riders[]` item in the recommended product with `price > 0` that the profile does not require -> `dontPayFor` with name + price. Riders are the upsell; default is OFF unless the need is explicit.
6. Duplicate coverage: if the same risk is covered by two products/riders in current subs -> `dontPayFor` the more expensive duplicate.
7. Premium tier: if `coveragePriority == false`, pick the base product that meets legal/real need, not the top package.

## Output shape (for the advisor to speak from)
```
recommendation: <exact DATA item name/id or "stay" or null>
why: <one short SI line, no sumniki>
dontPayFor:
  - <field-tied concrete item + price>
  - ...
```
Advisor turns this into short human SI text. If dontPayFor is long, lead with the biggest euro saver first.
