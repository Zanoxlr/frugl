"""B2 skin: add short Slovenian "why" strings to a B1 result, keyed on rule code.

Pure presentation — it reads the params the core already put on each item and
interpolates a template. No new numbers, no LLM. All copy is written WITHOUT
sumniki (c/s/z, never c-hacek/s-hacek/z-hacek), per the house style.
"""

import copy


def _num(value):
    """Trim a trailing .0 so 4.99 stays 4.99 but 35.0 reads as 35."""
    if value is None:
        return "?"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _why_unused_sport_addon(item):
    return "za %s placujes %s eur na mesec, sporta pa ne gledas - cista izguba" % (
        item["name"],
        _num(item["monthlyEur"]),
    )


def _why_mobile_rightsize(rec):
    used = rec.get("usedGB")
    used_clause = "porabis pa okoli %s GB, " % used if used else ""
    return (
        "placujes %s eur za %s GB, %s%s (%s) ti da dovolj hitrih podatkov za %s eur"
        % (
            _num(rec["fromMonthlyEur"]),
            _num(rec.get("fromDataGB")),
            used_clause,
            rec["toName"],
            rec["toOperator"],
            _num(rec["toMonthlyEur"]),
        )
    )


def _why_legacy_dopolnilno(item):
    return (
        "dopolnilno zdravstveno zavarovanje je od leta 2024 nadomestil obvezni OZP"
        " (zdaj %s eur na mesec prek place); ce ti se vedno zaracunavajo %s eur"
        " loceno, to najbrz placujes dvojno"
        % (_num(item.get("ozpMonthlyEur")), _num(item["monthlyEur"]))
    )


def _why_energy_tradeoff(rec):
    trade = rec["tradeoff"]
    unit = trade["lowestUnitPrice"]
    fixed = trade["lowestFixedFee"]
    return (
        "brez letne porabe (kwh) ne morem izracunati tocnega prihranka; ce porabis"
        " veliko, vzemi najnizjo ceno na kwh (%s, %s), ce malo, vzemi ponudbo brez"
        " mesecne takse (%s)"
        % (unit["provider"], _num(unit["unitRateEurPerKwh"]), fixed["provider"])
    )


def _why_energy_ranked(rec):
    best = rec["cheapest"]
    return (
        "za tvojo porabo je najugodnejsi %s (%s); ocena velja le za energijski del"
        " racuna" % (best["provider"], best["name"])
    )


def explain(result):
    """Return a deep copy of a B1 result with `why` strings added. Idempotent and
    side-effect free — the input result is never mutated."""
    out = copy.deepcopy(result)

    for item in out.get("dontPayFor", []):
        code = item.get("ruleCode")
        if code == "TELCO_UNUSED_SPORT_ADDON":
            item["why"] = _why_unused_sport_addon(item)
        elif code == "INS_LEGACY_DOPOLNILNO":
            item["why"] = _why_legacy_dopolnilno(item)

    rec = out.get("recommendation")
    if isinstance(rec, dict):
        if "mobile" in rec:
            rec["mobile"]["why"] = _why_mobile_rightsize(rec["mobile"])
        if rec.get("ruleCode") == "ENERGY_NO_USAGE_TRADEOFF":
            rec["why"] = _why_energy_tradeoff(rec)
        elif rec.get("ruleCode") == "ENERGY_RANKED_BY_USAGE":
            rec["why"] = _why_energy_ranked(rec)

    return out
