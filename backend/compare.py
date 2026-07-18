"""B1 core: given a user's State (household facts + current subscription lines) and
their per-vertical Preferences (signals), deterministically compute the right-fit
option, the euro savings, and what to stop paying for.

No LLM. Every function returns bare numbers plus rule codes; the Slovenian "why"
strings are layered on by reasons.py so B1 and B2 share identical math.

    compare(vertical, state, preferences, cat)

`state`       = { household:{...}, currentSubscriptions:[ {vertical,kind,provider,planName,monthlyEur,attributes} ] }
`preferences` = { vertical, signals:{...}, ... }

Household facts are read from `state.household` and merged with `preferences.signals`
at the point each rule needs them. Current lines are read by their explicit `kind`
(with a name-based fallback when kind is absent).
"""

import math

from . import catalog as catalog_module

_MIN_MATCH_LEN = 4  # ignore catalog names too short to match a line safely


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _line_name(line):
    return line.get("planName") or line.get("name") or ""


def _line_price(line):
    return float(line.get("monthlyEur") or 0.0)


def _attr(line, key, default=None):
    return (line.get("attributes") or {}).get(key, default)


def _round2(value):
    return None if value is None else round(value + 0.0, 2)


def _lines_for(state, vertical):
    subs = state.get("currentSubscriptions")
    if not isinstance(subs, list):
        return []
    return [s for s in subs if isinstance(s, dict) and s.get("vertical") == vertical]


def data_threshold_gb(need):
    """Map dataNeedGB ('low'/'mid'/'high'/'unlimited'/number/None) to a full-speed GB floor."""
    if need is None:
        return 0.0
    if isinstance(need, (int, float)):
        return float(need)
    text = str(need).strip().lower()
    keywords = {"low": 5.0, "mid": 20.0, "high": 100.0, "unlimited": math.inf}
    if text in keywords:
        return keywords[text]
    try:
        return float(text)
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------- #
# Telco
# --------------------------------------------------------------------------- #
_TV_PACK_KEYWORDS = {
    "sport": ("arena", "sport", "eurosport"),
    "movies": ("hbo", "cinestar", "filmbox", "skyshowtime", "voyo", "netflix"),
    "kids": ("minimax", "nick", "cartoon", "baby tv", "jimjam"),
    "balkan": ("balkan", "pink"),
    "adult": ("hustler", "xxx", "brazzers", "erotic", "playboy"),
}


def _infer_telco_kind(line, cat):
    name = _line_name(line).lower()
    for addon in cat["telco"]["tvAddons"]:
        if len(addon["name"]) >= _MIN_MATCH_LEN and addon["name"].lower() in name:
            return "tv_addon"
    for plan in cat["telco"]["mobilePlans"]:
        if len(plan["name"]) >= _MIN_MATCH_LEN and plan["name"].lower() in name:
            return "mobile"
    if "mobil" in name:
        return "mobile"
    return "fixed"


def _pack_type(line):
    """Which TV-pack category a tv_addon is, from attributes.packType or the name."""
    explicit = _attr(line, "packType")
    if explicit:
        return explicit
    name = _line_name(line).lower()
    for pack, words in _TV_PACK_KEYWORDS.items():
        if any(w in name for w in words):
            return pack
    return "other"


def _used_packs(signals):
    """Canonical set of TV packs the user actually watches. Prefers the explicit
    list; falls back to watchesSport so the older signal still works."""
    packs = signals.get("paidTvPacksUsed")
    if not isinstance(packs, list):
        packs = None  # a mistyped string would iterate chars into a garbage set; ignore it
    if packs is not None:
        return {str(p).lower() for p in packs}
    if signals.get("watchesSport"):
        return {"sport"}
    return set()  # watchesSport false/None -> nothing named as wanted


def _cheapest_mobile(cat, threshold, operator=None):
    pool = cat["telco"]["mobilePlans"]
    if operator:
        pool = [p for p in pool if p["operator"].lower() == operator.lower()]
    eligible = [
        p for p in pool
        if p["priceEur"] and p["fullSpeedGB"] is not None and p["fullSpeedGB"] >= threshold
        and not p.get("restricted")  # skip age/eligibility-gated plans (e.g. Senior MIO)
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda p: (p["priceEur"], p["operator"]))


def compare_telco(current, household, signals, cat):
    dont_pay_for = []
    recommendation = {}
    recommended_total = 0.0
    notes = []

    used_packs = _used_packs(signals)
    threshold = data_threshold_gb(signals.get("dataNeedGB"))
    open_switch = signals.get("openToSwitchOperator")
    wants_fixed = signals.get("wantsFixedBroadband")
    line_count = household.get("lineCount") or 0

    mobile_swaps = []
    mobile_lines_seen = 0

    for line in current:
        kind = line.get("kind") or _infer_telco_kind(line, cat)
        price = _line_price(line)
        name = _line_name(line)

        if kind == "tv_addon":
            if price > 0 and _pack_type(line) not in used_packs:
                dont_pay_for.append(
                    {
                        "name": name,
                        "monthlyEur": _round2(price),
                        "packType": _pack_type(line),
                        "ruleCode": "TELCO_UNUSED_TV_PACK",
                    }
                )
            else:
                recommended_total += price

        elif kind == "mobile":
            mobile_lines_seen += 1
            # Same-operator downsize unless the user is open to switching operator.
            operator = None if open_switch or open_switch is None else (line.get("provider") or "")
            best = _cheapest_mobile(cat, threshold, operator=operator)
            if best and best["priceEur"] < price:
                # Rightsize each entered line on its own real price — honest, no
                # multiplying a single line's saving by an unseen SIM count.
                mobile_swaps.append(
                    {
                        "from": name,
                        "fromMonthlyEur": _round2(price),
                        "fromDataGB": _attr(line, "dataGB"),
                        "toName": best["name"],
                        "toOperator": best["operator"],
                        "toMonthlyEur": _round2(best["priceEur"]),
                        "usedGB": signals.get("dataNeedGB"),
                        "ruleCode": "TELCO_MOBILE_RIGHTSIZE",
                    }
                )
                recommended_total += best["priceEur"]
            else:
                recommended_total += price

        else:  # fixed internet + TV bundle
            if wants_fixed is False and price > 0:
                # They don't want home broadband/TV -> the whole bundle is droppable.
                dont_pay_for.append(
                    {
                        "name": name,
                        "monthlyEur": _round2(price),
                        "ruleCode": "TELCO_DROP_UNUSED_FIXED",
                    }
                )
            else:
                recommended_total += price  # honest default: keep (channels/speed not comparable like-for-like)

    if mobile_swaps:
        recommendation["mobile"] = mobile_swaps[0]
        if len(mobile_swaps) > 1:
            recommendation["mobile"]["additionalLinesSwapped"] = len(mobile_swaps) - 1
    # If the household has more SIMs than lines we can see, guide without faking euros.
    if mobile_swaps and line_count > mobile_lines_seen:
        notes.append("imas %d SIM linij; enak prihranek preveri na vsaki" % line_count)

    current_total = sum(_line_price(l) for l in current)
    monthly_savings = _round2(current_total - recommended_total)
    return _result("telco", current_total, recommendation or None, recommended_total,
                   dont_pay_for, monthly_savings, notes)


# --------------------------------------------------------------------------- #
# Energy
# --------------------------------------------------------------------------- #
_NIGHT_SHARE = {"mostly_day": 0.15, "even": 0.35, "mostly_night": 0.55}
_DEFAULT_NIGHT_SHARE = 0.25


def _ranking_rate(plan, meter_type, day_night_split):
    """Unit rate to rank on, honoring meter type. single_ET -> ET (else VT). A dual
    VT/MT meter blends VT and MT by the night share (default ~25% when unknown)."""
    if meter_type == "dual_VT_MT" and plan["vtRate"] is not None and plan["mtRate"] is not None:
        night = _NIGHT_SHARE.get(day_night_split, _DEFAULT_NIGHT_SHARE)
        return plan["vtRate"] * (1 - night) + plan["mtRate"] * night
    return plan["etRate"] if plan["etRate"] is not None else plan["vtRate"]


def _energy_candidates(plans, signals):
    """Filter the plan set by price-certainty and contract-lock preferences before
    ranking. Nulls mean 'no filter'."""
    out = list(plans)
    pref = signals.get("priceCertaintyPref")
    if pref == "price_locked":
        out = [p for p in out if p["isFixed"]]
    elif pref == "cheapest_now":
        out = [p for p in out if not p["isFixed"]]
    lock = signals.get("contractLockTolerance")
    if lock == "no_lock":
        out = [p for p in out if (p["commitmentMonths"] or 0) == 0]
    return out or list(plans)  # never filter down to nothing


def _energy_pick(plan, rate):
    return {
        "provider": plan["provider"],
        "name": plan["name"],
        "unitRateEurPerKwh": _round2(rate) if rate is not None else None,
        "fixedMonthlyEur": plan["fixedMonthlyEur"],
        "isFixed": plan["isFixed"],
    }


def compare_energy(current, household, signals, cat):
    current_total = sum(_line_price(l) for l in current)
    meter = signals.get("meterType")
    split = signals.get("dayNightSplit")

    def rate_of(plan):
        return _ranking_rate(plan, meter, split)

    elec = [p for p in _energy_candidates(cat["energy"]["electricity"], signals) if rate_of(p) is not None]
    annual_kwh = signals.get("annualKwh")

    recommendation = {}
    notes = []

    if annual_kwh is None:
        # Usage unknown: cheapest unit price is wrong when fixed fees differ, so give
        # the trade-off and refuse to quote a saving.
        lowest_unit = min(elec, key=rate_of)
        priced = [p for p in elec if p["fixedMonthlyEur"] is not None]
        lowest_fixed = min(priced, key=lambda p: (p["fixedMonthlyEur"], rate_of(p)))
        recommendation["electricity"] = {
            "tradeoff": {
                "lowestUnitPrice": _energy_pick(lowest_unit, rate_of(lowest_unit)),
                "lowestFixedFee": _energy_pick(lowest_fixed, rate_of(lowest_fixed)),
            },
            "ruleCode": "ENERGY_NO_USAGE_TRADEOFF",
        }
        notes.append("ni podatka o letni porabi (kwh); prihranka ne morem tocno izracunati")
        monthly_savings = None
    else:
        def annual_cost(plan):
            return annual_kwh * rate_of(plan) + 12 * (plan["fixedMonthlyEur"] or 0.0)

        best = min(elec, key=annual_cost)
        recommendation["electricity"] = {
            "cheapest": _energy_pick(best, rate_of(best)),
            "estimatedAnnualEnergyEur": _round2(annual_cost(best)),
            "ruleCode": "ENERGY_RANKED_BY_USAGE",
        }
        notes.append("ocena velja le za energijski del racuna; omreznina, dajatve in ddv"
                     " so enaki ne glede na dobavitelja")
        monthly_savings = None  # current line is an all-in bill, not decomposable

    # Gas: only when the user actually has gas. Recommend the cheapest gas plan and,
    # if one supplier is cheapest for both, nudge a dual-fuel bundle.
    if signals.get("hasGas"):
        gas_kwh = signals.get("annualGasKwh")
        gas_plans = [g for g in cat["energy"]["gas"] if g["etRate"] is not None]
        if gas_plans:
            if gas_kwh is None:
                gas_best = min(gas_plans, key=lambda g: g["etRate"])
            else:
                gas_best = min(gas_plans, key=lambda g: gas_kwh * g["etRate"] + 12 * (g["fixedMonthlyEur"] or 0.0))
            recommendation["gas"] = {
                "cheapest": _energy_pick(gas_best, gas_best["etRate"]),
                "ruleCode": "ENERGY_GAS_RANKED",
            }
            elec_provider = recommendation["electricity"].get("cheapest", {}).get("provider") \
                or recommendation["electricity"].get("tradeoff", {}).get("lowestUnitPrice", {}).get("provider")
            if elec_provider and elec_provider == gas_best["provider"]:
                recommendation["dualFuel"] = {
                    "provider": gas_best["provider"],
                    "ruleCode": "ENERGY_DUAL_FUEL_BUNDLE",
                }
                notes.append("isti dobavitelj je najugodnejsi za elektriko in plin;"
                             " dvojno gorivo pri enem ponudniku poenostavi racun")

    recommended_total = None  # energy savings are advisory in this dataset
    return _result("energy", current_total, recommendation or None, recommended_total,
                   [], monthly_savings, notes)


# --------------------------------------------------------------------------- #
# Insurance
# --------------------------------------------------------------------------- #
def _infer_insurance_kind(line):
    name = _line_name(line).lower()
    if "dopolnilno" in name and "zdravstv" in name:
        return "legacy_dopolnilno"
    if "gap" in name:
        return "car_gap"
    if " ao" in name or "avtomob" in name or "odgovornost vozil" in name:
        return "car_ao"
    if "kasko" in name:
        return "car_kasko"
    return "other"


def compare_insurance(current, household, signals, cat):
    dont_pay_for = []
    ozp = cat["insurance"]["ozp"]["currentMonthlyEur"]
    financing = household.get("carFinancing")
    ownership = household.get("homeOwnership")
    health = signals.get("healthPrefs")
    health = health if isinstance(health, dict) else {}
    cover_elsewhere = signals.get("coverElsewhere")
    cover_elsewhere = cover_elsewhere if isinstance(cover_elsewhere, dict) else {}

    for line in current:
        kind = line.get("kind") or _infer_insurance_kind(line)
        price = _line_price(line)  # extraEur is null in data -> the line's own price
        drop = None

        if kind == "legacy_dopolnilno":
            # Derived, not gated on a preference: the abolished product's presence IS
            # the finding, so this fires whenever the line exists.
            drop = {"ruleCode": "INS_LEGACY_DOPOLNILNO", "ozpMonthlyEur": ozp}
        elif kind == "car_gap" and financing == "owned_outright":
            drop = {"ruleCode": "INS_GAP_OWNED_OUTRIGHT"}
        elif kind == "home_structure" and ownership == "tenant":
            drop = {"ruleCode": "INS_TENANT_STRUCTURE"}
        elif kind == "health_rider":
            rider = _attr(line, "riderType")
            if rider == "dental" and health.get("expectsDentalWork") is False:
                drop = {"ruleCode": "INS_UNUSED_HEALTH_RIDER", "riderType": "dental"}
            elif rider != "dental" and health.get("valuesFasterPrivateAccess") is False:
                drop = {"ruleCode": "INS_UNUSED_HEALTH_RIDER", "riderType": rider or "specialist"}
        elif kind == "accident" and cover_elsewhere.get("personalAccident") is True:
            drop = {"ruleCode": "INS_DUPLICATE_COVER", "coverType": "accident"}
        elif kind == "assistance" and cover_elsewhere.get("roadsideAssist") is True:
            drop = {"ruleCode": "INS_DUPLICATE_COVER", "coverType": "assistance"}

        if drop:
            drop.update({"name": _line_name(line), "monthlyEur": _round2(price)})
            dont_pay_for.append(drop)

    current_total = sum(_line_price(l) for l in current)
    # No exact premiums in the dataset -> nothing priced to switch to; value is the drops.
    monthly_savings = _round2(sum(d["monthlyEur"] for d in dont_pay_for)) if dont_pay_for else None
    recommended_total = _round2(current_total - (monthly_savings or 0.0))
    return _result("insurance", current_total, None, recommended_total,
                   dont_pay_for, monthly_savings, [])


# --------------------------------------------------------------------------- #
# Shared result builder + dispatch
# --------------------------------------------------------------------------- #
def _result(vertical, current_total, recommendation, recommended_total, dont_pay_for, monthly_savings, notes):
    return {
        "vertical": vertical,
        "currentMonthlyEur": _round2(current_total),  # always pass-through
        "recommendation": recommendation,
        "recommendedMonthlyEur": _round2(recommended_total),
        "dontPayFor": dont_pay_for,
        "monthlySavingsEur": monthly_savings,
        # annualSavings is null exactly when monthly is null — never 0-as-unknown.
        "annualSavingsEur": _round2(monthly_savings * 12) if monthly_savings is not None else None,
        "notes": notes,
    }


_DISPATCH = {
    "telco": compare_telco,
    "energy": compare_energy,
    "insurance": compare_insurance,
}


def compare(vertical, state, preferences, cat=None):
    if vertical not in _DISPATCH:
        raise ValueError("unknown vertical: %r" % (vertical,))
    if cat is None:
        cat = catalog_module.load()
    state = state or {}
    household = state.get("household")
    household = household if isinstance(household, dict) else {}
    signals = (preferences or {}).get("signals")
    signals = signals if isinstance(signals, dict) else {}  # a list/str here 500s every rule
    current = _lines_for(state, vertical)
    return _DISPATCH[vertical](current, household, signals, cat)
