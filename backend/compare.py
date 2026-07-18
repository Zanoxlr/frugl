"""B1 core: given current subscriptions + a needs profile, deterministically
compute the right-fit option, the euro savings, and what to stop paying for.

No LLM. Every function returns bare numbers plus rule codes; the Slovenian "why"
strings are layered on separately by reasons.py so B1 and B2 share identical math.

`current` is a list of the user's current lines for one vertical, each at least
{provider, planName|name, monthlyEur}; an optional `kind` overrides classification.
`needs` is a NeedsProfile (needs_profile.schema.json) for that vertical.
"""

import math

from . import catalog as catalog_module

_MIN_MATCH_LEN = 4  # ignore catalog names too short to match a line safely


def _line_name(line):
    return (line.get("planName") or line.get("name") or "")


def _line_price(line):
    return float(line.get("monthlyEur") or 0.0)


def _round2(value):
    return None if value is None else round(value + 0.0, 2)


def data_threshold_gb(need):
    """Map a NeedsProfile dataNeedGB ('low'/'mid'/'high'/'unlimited'/number/None)
    to a full-speed GB floor."""
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
def _classify_telco_line(line, cat):
    if line.get("kind"):
        return line["kind"]
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


def _is_sport_addon(name):
    low = name.lower()
    return "arena" in low or "sport" in low


def _cheapest_mobile(cat, threshold):
    eligible = [
        p
        for p in cat["telco"]["mobilePlans"]
        if p["priceEur"] and p["fullSpeedGB"] is not None and p["fullSpeedGB"] >= threshold
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda p: (p["priceEur"], p["operator"]))


def compare_telco(current, needs, cat):
    prefs = needs.get("telco") or {}
    current_total = sum(_line_price(l) for l in current)

    dont_pay_for = []
    recommendation = {}
    recommended_total = 0.0

    for line in current:
        kind = _classify_telco_line(line, cat)
        price = _line_price(line)
        name = _line_name(line)

        if kind == "tv_addon":
            watches_sport = prefs.get("watchesSport")
            if not watches_sport and price > 0 and _is_sport_addon(name):
                dont_pay_for.append(
                    {
                        "name": name,
                        "monthlyEur": _round2(price),
                        "ruleCode": "TELCO_UNUSED_SPORT_ADDON",
                    }
                )
            else:
                recommended_total += price  # a wanted add-on stays
        elif kind == "mobile":
            threshold = data_threshold_gb(prefs.get("dataNeedGB"))
            best = _cheapest_mobile(cat, threshold)
            if best and best["priceEur"] < price:
                recommendation["mobile"] = {
                    "from": name,
                    "fromMonthlyEur": _round2(price),
                    "toName": best["name"],
                    "toOperator": best["operator"],
                    "toMonthlyEur": _round2(best["priceEur"]),
                    "usedGB": prefs.get("dataNeedGB"),
                    "fromDataGB": _current_line_data_gb(name, cat),
                    "ruleCode": "TELCO_MOBILE_RIGHTSIZE",
                }
                recommended_total += best["priceEur"]
            else:
                recommended_total += price  # already right-sized
        else:  # fixed
            recommended_total += price

    monthly_savings = _round2(current_total - recommended_total)
    return _result(
        "telco",
        current_total,
        recommendation or None,
        recommended_total,
        dont_pay_for,
        monthly_savings,
        notes=[],
    )


def _current_line_data_gb(name, cat):
    low = name.lower()
    for plan in cat["telco"]["mobilePlans"]:
        if len(plan["name"]) >= _MIN_MATCH_LEN and plan["name"].lower() in low:
            return plan.get("dataGB")
    return None


# --------------------------------------------------------------------------- #
# Energy
# --------------------------------------------------------------------------- #
def _rank_key_unit(plan):
    return plan["unitRateEurPerKwh"]


def compare_energy(current, needs, cat):
    prefs = needs.get("energy") or {}
    current_total = sum(_line_price(l) for l in current)
    plans = [p for p in cat["energy"]["electricity"] if p["unitRateEurPerKwh"] is not None]

    annual_kwh = prefs.get("annualKwh")

    if annual_kwh is None:
        # Usage unknown: cheapest unit price is not the answer when fixed fees
        # differ, so present the trade-off and refuse to quote a saving.
        lowest_unit = min(plans, key=lambda p: p["unitRateEurPerKwh"])
        priced = [p for p in plans if p["fixedMonthlyEur"] is not None]
        lowest_fixed = min(
            priced, key=lambda p: (p["fixedMonthlyEur"], p["unitRateEurPerKwh"])
        )
        recommendation = {
            "tradeoff": {
                "lowestUnitPrice": _energy_pick(lowest_unit),
                "lowestFixedFee": _energy_pick(lowest_fixed),
            },
            "ruleCode": "ENERGY_NO_USAGE_TRADEOFF",
        }
        return _result(
            "energy",
            current_total,
            recommendation,
            None,
            [],
            None,
            notes=[
                "ni podatka o letni porabi (kwh); prihranka ne morem tocno izracunati"
            ],
        )

    # Usage known: rank by annual energy cost, name the cheapest. Savings stay
    # null because the current line is an all-in bill, not an energy-only figure.
    def annual_cost(plan):
        return annual_kwh * plan["unitRateEurPerKwh"] + 12 * (plan["fixedMonthlyEur"] or 0.0)

    best = min(plans, key=annual_cost)
    recommendation = {
        "cheapest": _energy_pick(best),
        "estimatedAnnualEnergyEur": _round2(annual_cost(best)),
        "ruleCode": "ENERGY_RANKED_BY_USAGE",
    }
    return _result(
        "energy",
        current_total,
        recommendation,
        None,
        [],
        None,
        notes=[
            "ocena velja le za energijski del racuna; omreznina, dajatve in ddv so"
            " enaki ne glede na dobavitelja"
        ],
    )


def _energy_pick(plan):
    return {
        "provider": plan["provider"],
        "name": plan["name"],
        "unitRateEurPerKwh": plan["unitRateEurPerKwh"],
        "fixedMonthlyEur": plan["fixedMonthlyEur"],
        "assumedVt": plan["assumedVt"],
    }


# --------------------------------------------------------------------------- #
# Insurance
# --------------------------------------------------------------------------- #
def _classify_insurance_line(line):
    if line.get("kind"):
        return line["kind"]
    name = _line_name(line).lower()
    if "dopolnilno" in name and "zdravstv" in name:
        return "legacy_dopolnilno"
    if " ao" in name or "avtomob" in name or "odgovornost" in name:
        return "car_ao"
    return "other"


def compare_insurance(current, needs, cat):
    prefs = needs.get("insurance") or {}
    current_total = sum(_line_price(l) for l in current)

    dont_pay_for = []
    for line in current:
        kind = _classify_insurance_line(line)
        price = _line_price(line)  # extraEur is null in data -> use the line's own price
        if kind == "legacy_dopolnilno" and prefs.get("paysLegacyDopolnilno"):
            dont_pay_for.append(
                {
                    "name": _line_name(line),
                    "monthlyEur": _round2(price),
                    "ruleCode": "INS_LEGACY_DOPOLNILNO",
                    "ozpMonthlyEur": cat["insurance"]["ozp"]["currentMonthlyEur"],
                }
            )

    # No exact premiums exist in the dataset, so there is nothing priced to switch
    # to; the entire value is in the droppable lines.
    monthly_savings = _round2(sum(d["monthlyEur"] for d in dont_pay_for)) if dont_pay_for else None
    recommended_total = _round2(current_total - (monthly_savings or 0.0))
    return _result(
        "insurance",
        current_total,
        None,
        recommended_total,
        dont_pay_for,
        monthly_savings,
        notes=[],
    )


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


def compare(vertical, current, needs, cat=None):
    if vertical not in _DISPATCH:
        raise ValueError("unknown vertical: %r" % (vertical,))
    if cat is None:
        cat = catalog_module.load()
    return _DISPATCH[vertical](current or [], needs or {}, cat)
