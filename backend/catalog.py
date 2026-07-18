"""Normalize the raw grounding data files into uniform, comparison-ready dicts.

The raw files carry real-world mess: two overlapping mobile catalogs, int-as-bool
flags, electricity unit prices as {VT,MT,ET} dicts but gas as bare numbers, nulls
scattered through price fields. Everything the compare engine needs is flattened
here so compare.py can stay a pure ruleset with no data-shape branching.

Nothing here is user-specific and nothing calls an LLM.
"""

import json
import math
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# telco_mvno.json is the authoritative HOT/BOB source (fresh scrape, carries the
# full-speed thresholds). The stale HOT/BOB rows in mobile_packages.json are these
# operators; drop them so we don't rank duplicate/contradictory plans.
_MVNO_OPERATORS = {"HOT", "BOB"}

# "(20 GB at full 150/50 Mbit/s ...)" -> 20. Matches only the full-speed phrase,
# never the EU-roaming "14.8 GB" numbers elsewhere in the text.
_FULL_SPEED_RE = re.compile(r"\((\d+)\s*GB\s+at\s+full", re.IGNORECASE)


def _load(*parts):
    with open(os.path.join(DATA_DIR, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def _to_bool(value):
    """int 0/1, bool, or None -> bool."""
    return bool(value)


# --------------------------------------------------------------------------- #
# Telco
# --------------------------------------------------------------------------- #
def _premium_full_speed_gb(data_gb, unlimited):
    """Full-speed GB for a mobile_packages.json row. dataGB is the full-speed cap
    when present; an uncapped unlimited plan (dataGB null) is treated as inf.
    We never parse the HTML description here — its GB figure is EU-roaming."""
    if data_gb is not None:
        return float(data_gb)
    return math.inf if unlimited else None


def _mvno_full_speed_gb(plan):
    """Full-speed GB for a telco_mvno.json plan: dataGB if capped, else the
    '(N GB at full ...)' phrase, else inf for a genuinely uncapped plan."""
    if plan.get("dataGB") is not None:
        return float(plan["dataGB"])
    for text in plan.get("keyFeatures", []) + [plan.get("notes", "")]:
        m = _FULL_SPEED_RE.search(text or "")
        if m:
            return float(m.group(1))
    return math.inf if plan.get("unlimited") else None


def _load_mobile_plans():
    plans = []

    for row in _load("telco", "mobile_packages.json"):
        operator = row["operator"]
        if operator in _MVNO_OPERATORS:
            continue  # use the richer telco_mvno.json rows instead
        price = row.get("priceEur")
        if not price:  # null-guard: unpriced rows can't be ranked
            continue
        plans.append(
            {
                "operator": operator,
                "name": row["group"],
                "priceEur": float(price),
                "dataGB": row.get("dataGB"),
                "unlimited": _to_bool(row.get("unlimited")),
                "fullSpeedGB": _premium_full_speed_gb(
                    row.get("dataGB"), _to_bool(row.get("unlimited"))
                ),
                "restricted": row.get("restricted"),  # e.g. "senior" — excluded from general recs
                "source": "mobile_packages",
            }
        )

    for provider in _load("telco", "telco_mvno.json")["providers"]:
        operator = provider["provider"]
        for plan in provider["plans"]:
            if plan.get("type") != "mobile":
                continue  # skip data-only "internet" SIMs
            price = plan.get("monthlyEur")
            if not price:  # skip pay-per-use "bob 4 cente" (monthlyEur 0)
                continue
            plans.append(
                {
                    "operator": operator,
                    "name": plan["name"],
                    "priceEur": float(price),
                    "dataGB": plan.get("dataGB"),
                    "unlimited": _to_bool(plan.get("unlimited")),
                    "fullSpeedGB": _mvno_full_speed_gb(plan),
                    "source": "telco_mvno",
                }
            )

    return plans


def _load_tv_addons():
    addons = []
    for row in _load("telco", "tv_schemes.json"):
        if not _to_bool(row.get("isAddon")):
            continue
        price = row.get("addonPriceEur")
        if price is None:  # null-guard
            continue
        addons.append(
            {
                "operatorId": row.get("operatorId"),
                "name": row["name"],
                "priceEur": float(price),
            }
        )
    return addons


def _load_fix_packages():
    packages = []
    for op in _load("telco", "retail_prices.json")["operators"]:
        for pkg in op.get("packages", []):
            price = pkg.get("monthlyEur")
            if price is None:  # configurator-only rows have no price
                continue
            packages.append(
                {
                    "operator": op["operator"],
                    "name": pkg["name"],
                    "priceEur": float(price),
                }
            )
    return packages


# --------------------------------------------------------------------------- #
# Energy
# --------------------------------------------------------------------------- #
def _float_or_none(value):
    return float(value) if value is not None else None


def _load_energy():
    """Electricity carries VT/MT/ET rates (a {VT,MT,ET} dict); gas is a bare
    per-kWh number stored as etRate so the ranking code has one field to read.
    `unitRateEurPerKwh` is the default single-tariff rate (ET, else VT) kept for
    callers that don't care about meter type; compare.py picks the real rate by
    meterType from vt/mt/et."""
    electricity, gas = [], []
    for provider in _load("energy.json")["providers"]:
        for plan in provider["plans"]:
            raw = plan.get("energyEurPerKwh")
            if isinstance(raw, dict):
                et = _float_or_none(raw.get("ET"))
                vt = _float_or_none(raw.get("VT"))
                mt = _float_or_none(raw.get("MT"))
            else:  # gas: a single number
                et, vt, mt = _float_or_none(raw), None, None
            default = et if et is not None else vt
            entry = {
                "provider": provider["provider"],
                "name": plan["name"],
                "etRate": et,
                "vtRate": vt,
                "mtRate": mt,
                "unitRateEurPerKwh": default,
                "assumedVt": et is None and vt is not None,
                "fixedMonthlyEur": plan.get("fixedMonthlyEur"),
                "isFixed": "fixed" in (plan.get("greenOrFixed") or "").lower(),
                "commitmentMonths": plan.get("commitmentMonths"),
            }
            if plan.get("utility") == "gas":
                gas.append(entry)
            else:
                electricity.append(entry)
    return {"electricity": electricity, "gas": gas}


# --------------------------------------------------------------------------- #
# Insurance
# --------------------------------------------------------------------------- #
def _load_insurance():
    products = []
    for provider in _load("insurance.json")["providers"]:
        for prod in provider["products"]:
            products.append(
                {
                    "provider": provider["provider"],
                    "name": prod["name"],
                    "type": prod.get("type"),
                    "monthlyRange": prod.get("typicalMonthlyEurRange"),
                    "annualRange": prod.get("typicalAnnualEurRange"),
                }
            )
    baseline = _load("insurance.json")["publicCoverBaseline"]["ozp"]
    return {
        "products": products,
        "ozp": {
            "name": baseline["name"],
            "currentMonthlyEur": baseline["currentMonthlyEur"],
            "since": baseline.get("currentSince"),
        },
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def load():
    """Return the fully normalized catalog. Cheap enough to call per request."""
    return {
        "telco": {
            "mobilePlans": _load_mobile_plans(),
            "tvAddons": _load_tv_addons(),
            "fixPackages": _load_fix_packages(),
        },
        "energy": _load_energy(),
        "insurance": _load_insurance(),
    }


def load_counts():
    """Small conformance summary used by the smoke check."""
    cat = load()
    return {
        "mobilePlans": len(cat["telco"]["mobilePlans"]),
        "tvAddons": len(cat["telco"]["tvAddons"]),
        "fixPackages": len(cat["telco"]["fixPackages"]),
        "electricity": len(cat["energy"]["electricity"]),
        "gas": len(cat["energy"]["gas"]),
        "insuranceProducts": len(cat["insurance"]["products"]),
        "ozpMonthlyEur": cat["insurance"]["ozp"]["currentMonthlyEur"],
    }


if __name__ == "__main__":
    print(json.dumps(load_counts(), indent=2))
