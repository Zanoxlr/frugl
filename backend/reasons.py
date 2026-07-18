"""B2 skin: add short Slovenian "why" strings to a B1 result, keyed on rule code.

Pure presentation — reads the params the core already attached to each item and
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


# --- dontPayFor rules ------------------------------------------------------- #
def _why_unused_tv_pack(item):
    return "za %s placujes %s eur na mesec, pa tega paketa ne gledas - cista izguba" % (
        item["name"], _num(item["monthlyEur"]))


def _why_drop_unused_fixed(item):
    return "za %s placujes %s eur na mesec za domaci net in tv, ki ga ne rabis" % (
        item["name"], _num(item["monthlyEur"]))


def _why_legacy_dopolnilno(item):
    return ("dopolnilno zdravstveno zavarovanje je od leta 2024 nadomestil obvezni OZP"
            " (zdaj %s eur na mesec prek place); ce ti se vedno zaracunavajo %s eur"
            " loceno, to najbrz placujes dvojno" % (
                _num(item.get("ozpMonthlyEur")), _num(item["monthlyEur"])))


def _why_gap_owned(item):
    return ("GAP kritje (%s eur) ima smisel samo pri leasingu ali kreditu; avto je tvoj,"
            " zato je odvec" % _num(item["monthlyEur"]))


def _why_tenant_structure(item):
    return ("kot najemnik ne zavarujes zgradbe, to je lastnikova stvar; %s (%s eur) je odvec"
            % (item["name"], _num(item["monthlyEur"])))


def _why_unused_health_rider(item):
    return ("%s (%s eur) je prostovoljno dodatno zdravstveno; obvezni sistem ze krije osnovo,"
            " ti pa tega ne rabis" % (item["name"], _num(item["monthlyEur"])))


def _why_duplicate_cover(item):
    return "%s (%s eur) ze imas krito drugje, torej placujes dvojno" % (
        item["name"], _num(item["monthlyEur"]))


_DONT_PAY_WHY = {
    "TELCO_UNUSED_TV_PACK": _why_unused_tv_pack,
    "TELCO_DROP_UNUSED_FIXED": _why_drop_unused_fixed,
    "INS_LEGACY_DOPOLNILNO": _why_legacy_dopolnilno,
    "INS_GAP_OWNED_OUTRIGHT": _why_gap_owned,
    "INS_TENANT_STRUCTURE": _why_tenant_structure,
    "INS_UNUSED_HEALTH_RIDER": _why_unused_health_rider,
    "INS_DUPLICATE_COVER": _why_duplicate_cover,
}


# --- recommendation rules --------------------------------------------------- #
def _why_mobile_rightsize(rec):
    used = rec.get("usedGB")
    used_clause = "porabis pa okoli %s GB, " % used if used else ""
    base = ("placujes %s eur za %s GB, %s%s (%s) ti da dovolj hitrih podatkov za %s eur" % (
        _num(rec["fromMonthlyEur"]), _num(rec.get("fromDataGB")), used_clause,
        rec["toName"], rec["toOperator"], _num(rec["toMonthlyEur"])))
    if (rec.get("lineCount") or 1) > 1:
        base += " (velja na %s linije)" % _num(rec["lineCount"])
    return base


def _why_energy_tradeoff(rec):
    trade = rec["tradeoff"]
    unit, fixed = trade["lowestUnitPrice"], trade["lowestFixedFee"]
    return ("brez letne porabe (kwh) ne morem izracunati tocnega prihranka; ce porabis"
            " veliko, vzemi najnizjo ceno na kwh (%s, %s), ce malo, vzemi ponudbo brez"
            " mesecne takse (%s)" % (unit["provider"], _num(unit["unitRateEurPerKwh"]),
                                     fixed["provider"]))


def _why_energy_ranked(rec):
    best = rec["cheapest"]
    return ("za tvojo porabo je najugodnejsi %s (%s); ocena velja le za energijski del racuna"
            % (best["provider"], best["name"]))


def _why_gas_ranked(rec):
    return "za plin je najugodnejsi %s" % rec["cheapest"]["provider"]


def _why_dual_fuel(rec):
    return ("isti dobavitelj %s je najugodnejsi za elektriko in plin; dvojno gorivo pri"
            " enem ponudniku poenostavi racun" % rec["provider"])


_REC_WHY = {
    "TELCO_MOBILE_RIGHTSIZE": _why_mobile_rightsize,
    "ENERGY_NO_USAGE_TRADEOFF": _why_energy_tradeoff,
    "ENERGY_RANKED_BY_USAGE": _why_energy_ranked,
    "ENERGY_GAS_RANKED": _why_gas_ranked,
    "ENERGY_DUAL_FUEL_BUNDLE": _why_dual_fuel,
}


def explain(result):
    """Return a deep copy of a B1 result with `why` strings added. Side-effect free."""
    out = copy.deepcopy(result)

    for item in out.get("dontPayFor", []):
        fn = _DONT_PAY_WHY.get(item.get("ruleCode"))
        if fn:
            item["why"] = fn(item)

    rec = out.get("recommendation")
    if isinstance(rec, dict):
        # recommendation is a bag of sub-objects (mobile / electricity / gas / dualFuel),
        # each carrying its own ruleCode.
        for node in rec.values():
            if isinstance(node, dict):
                fn = _REC_WHY.get(node.get("ruleCode"))
                if fn:
                    node["why"] = fn(node)

    return out
