"""End-to-end tests for the price-comparison calculator (State + Preferences model).

Covers the three Marko happy paths, every high-value-next rule (with synthetic
lines), the adversary edges, the B1==B2 numbers invariant, the water skip, and the
sumnik-free reasons copy.
"""

import copy
import json
import os

import pytest

from backend import catalog, compare, reasons

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
FIXTURES = os.path.join(HERE, "fixtures")

SUMNIKI = set("čšžČŠŽ")


@pytest.fixture(scope="module")
def cat():
    return catalog.load()


@pytest.fixture(scope="module")
def demo():
    with open(os.path.join(ROOT, "data", "demo_user.json"), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def state(demo):
    """A fresh copy each test so mutations don't leak."""
    return copy.deepcopy(demo)


def prefs(vertical):
    with open(os.path.join(FIXTURES, "marko_%s.preferences.json" % vertical), encoding="utf-8") as fh:
        return json.load(fh)


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)


def _strip_why(obj):
    if isinstance(obj, dict):
        return {k: _strip_why(v) for k, v in obj.items() if k != "why"}
    if isinstance(obj, list):
        return [_strip_why(v) for v in obj]
    return obj


def ins_state(household=None, lines=None):
    """A minimal insurance state for the synthetic keep/drop rules."""
    return {"household": household or {}, "currentSubscriptions": lines or []}


# --------------------------------------------------------------------------- #
# Catalog conformance
# --------------------------------------------------------------------------- #
def test_catalog_counts_nonzero():
    counts = catalog.load_counts()
    assert counts["mobilePlans"] > 0
    assert counts["electricity"] > 0
    assert counts["ozpMonthlyEur"] == 39.36


def test_mvno_dedup_and_full_speed(cat):
    bob = [p for p in cat["telco"]["mobilePlans"] if p["operator"] == "BOB"]
    assert any(p["name"] == "zeleni bob" for p in bob)
    assert all(p["source"] == "telco_mvno" for p in bob)
    assert next(p for p in bob if p["name"] == "zeleni bob")["fullSpeedGB"] == 20.0
    assert next(p for p in bob if p["name"] == "rdeci bob")["fullSpeedGB"] == 10.0


def test_energy_rates_split(cat):
    # electricity carries VT/MT/ET; the ranking blend needs all three where present.
    petrol = next(p for p in cat["energy"]["electricity"] if p["provider"] == "Petrol")
    assert petrol["vtRate"] is not None and petrol["mtRate"] is not None


# --------------------------------------------------------------------------- #
# Telco
# --------------------------------------------------------------------------- #
def test_telco_marko_saves_24_99(cat, state):
    r = compare.compare("telco", state, prefs("telco"), cat)
    assert r["currentMonthlyEur"] == 88.97
    assert r["monthlySavingsEur"] == 24.99
    assert r["annualSavingsEur"] == 299.88
    assert any(d["ruleCode"] == "TELCO_UNUSED_TV_PACK" for d in r["dontPayFor"])
    mob = r["recommendation"]["mobile"]
    assert mob["toName"] == "zeleni bob" and mob["toMonthlyEur"] == 7.99


def test_telco_threshold_excludes_too_small(cat, state):
    r = compare.compare("telco", state, prefs("telco"), cat)
    assert r["recommendation"]["mobile"]["toName"] != "rdeci bob"


def test_telco_uses_sport_pack_keeps_arena(cat, state):
    p = prefs("telco")
    p["signals"]["paidTvPacksUsed"] = ["sport"]
    r = compare.compare("telco", state, p, cat)
    assert all(d["ruleCode"] != "TELCO_UNUSED_TV_PACK" for d in r["dontPayFor"])
    assert r["monthlySavingsEur"] == 20.0  # only the mobile rightsize remains


def test_telco_same_operator_when_not_open_to_switch(cat, state):
    p = prefs("telco")
    p["signals"]["openToSwitchOperator"] = False
    r = compare.compare("telco", state, p, cat)
    mob = r["recommendation"]["mobile"]
    assert mob["toOperator"] == "A1"  # no MVNO jump
    assert mob["toName"] != "Senior MIO"  # age-restricted plan must be excluded
    assert mob["toName"] == "MiniMIO" and mob["toMonthlyEur"] == 15.99
    assert r["monthlySavingsEur"] == 16.99  # Arena 4.99 + (27.99 -> 15.99)


def test_restricted_plans_excluded_from_catalog_recs(cat):
    senior = next(p for p in cat["telco"]["mobilePlans"] if p["name"] == "Senior MIO")
    assert senior["restricted"] == "senior"
    best = compare._cheapest_mobile(cat, 15.0, operator="A1")
    assert best["name"] != "Senior MIO"


def test_telco_drop_unused_fixed(cat, state):
    p = prefs("telco")
    p["signals"]["wantsFixedBroadband"] = False
    r = compare.compare("telco", state, p, cat)
    assert any(d["ruleCode"] == "TELCO_DROP_UNUSED_FIXED" for d in r["dontPayFor"])
    assert r["monthlySavingsEur"] == 80.98  # fixed 55.99 + Arena 4.99 + mobile 20


def test_telco_multiple_mobile_lines_each_rightsized(cat, state):
    extra = copy.deepcopy(next(s for s in state["currentSubscriptions"] if s.get("kind") == "mobile"))
    state["currentSubscriptions"].append(extra)
    r = compare.compare("telco", state, prefs("telco"), cat)
    # Arena 4.99 + two mobile rightsizes of 20 each = 44.99 (honest per-line).
    assert r["monthlySavingsEur"] == 44.99
    assert r["recommendation"]["mobile"]["additionalLinesSwapped"] == 1


# --------------------------------------------------------------------------- #
# Energy
# --------------------------------------------------------------------------- #
def test_energy_no_usage_null_savings(cat, state):
    r = compare.compare("energy", state, prefs("energy"), cat)
    assert r["currentMonthlyEur"] == 41.9
    assert r["monthlySavingsEur"] is None
    assert r["annualSavingsEur"] is None
    trade = r["recommendation"]["electricity"]["tradeoff"]
    assert trade["lowestFixedFee"]["fixedMonthlyEur"] == 0
    assert trade["lowestFixedFee"]["name"] != trade["lowestUnitPrice"]["name"]


def test_energy_known_usage_ranks(cat, state):
    p = prefs("energy")
    p["signals"]["annualKwh"] = 3000
    r = compare.compare("energy", state, p, cat)
    assert r["recommendation"]["electricity"]["ruleCode"] == "ENERGY_RANKED_BY_USAGE"
    assert r["recommendation"]["electricity"]["estimatedAnnualEnergyEur"] > 0
    assert r["monthlySavingsEur"] is None


def test_energy_dual_meter_blends(cat, state):
    p = prefs("energy")
    p["signals"].update({"annualKwh": 4000, "meterType": "dual_VT_MT", "dayNightSplit": "mostly_night"})
    r = compare.compare("energy", state, p, cat)
    assert r["recommendation"]["electricity"]["cheapest"]["provider"]  # runs, picks one


def test_energy_gas_when_has_gas(cat, state):
    p = prefs("energy")
    p["signals"].update({"annualKwh": 4000, "hasGas": True, "annualGasKwh": 12000})
    r = compare.compare("energy", state, p, cat)
    assert "gas" in r["recommendation"]
    assert r["recommendation"]["gas"]["cheapest"]["provider"]


# --------------------------------------------------------------------------- #
# Insurance — legacy is now DERIVED from the line, plus the new keep/drop rules
# --------------------------------------------------------------------------- #
def test_insurance_legacy_fires_even_with_empty_signals(cat, state):
    # The whole point of deriving: no preference needed, the line's presence is enough.
    r = compare.compare("insurance", state, {"signals": {}}, cat)
    assert r["monthlySavingsEur"] == 35.0
    assert r["dontPayFor"][0]["ruleCode"] == "INS_LEGACY_DOPOLNILNO"
    assert r["dontPayFor"][0]["ozpMonthlyEur"] == 39.36


def test_insurance_gap_dropped_only_when_owned(cat):
    gap = [{"vertical": "insurance", "kind": "car_gap", "planName": "GAP kritje", "monthlyEur": 8.0}]
    owned = compare.compare("insurance", ins_state({"carFinancing": "owned_outright"}, gap), {}, cat)
    assert owned["monthlySavingsEur"] == 8.0
    assert owned["dontPayFor"][0]["ruleCode"] == "INS_GAP_OWNED_OUTRIGHT"
    leased = compare.compare("insurance", ins_state({"carFinancing": "leased"}, gap), {}, cat)
    assert leased["monthlySavingsEur"] is None  # keep GAP on a leased car


def test_insurance_tenant_structure_dropped(cat):
    home = [{"vertical": "insurance", "kind": "home_structure", "planName": "zavarovanje zgradbe", "monthlyEur": 12.0}]
    r = compare.compare("insurance", ins_state({"homeOwnership": "tenant"}, home), {}, cat)
    assert r["dontPayFor"][0]["ruleCode"] == "INS_TENANT_STRUCTURE"
    owner = compare.compare("insurance", ins_state({"homeOwnership": "owner"}, home), {}, cat)
    assert owner["monthlySavingsEur"] is None


def test_insurance_health_rider_dropped_by_pref(cat):
    line = [{"vertical": "insurance", "kind": "health_rider", "planName": "Zobje", "monthlyEur": 10.0,
             "attributes": {"riderType": "dental"}}]
    p = {"signals": {"healthPrefs": {"expectsDentalWork": False}}}
    r = compare.compare("insurance", ins_state({}, line), p, cat)
    assert r["dontPayFor"][0]["ruleCode"] == "INS_UNUSED_HEALTH_RIDER"


def test_insurance_duplicate_cover_dropped(cat):
    line = [{"vertical": "insurance", "kind": "accident", "planName": "nezgodno", "monthlyEur": 6.0}]
    p = {"signals": {"coverElsewhere": {"personalAccident": True}}}
    r = compare.compare("insurance", ins_state({}, line), p, cat)
    assert r["dontPayFor"][0]["ruleCode"] == "INS_DUPLICATE_COVER"


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("vertical", ["telco", "energy", "insurance"])
def test_null_price_line_doesnt_crash(cat, vertical):
    st = {"household": {}, "currentSubscriptions": [
        {"vertical": vertical, "provider": "X", "planName": "mystery", "monthlyEur": None}]}
    r = compare.compare(vertical, st, prefs(vertical), cat)
    assert r["currentMonthlyEur"] == 0.0


def test_empty_current_all_verticals(cat):
    for vertical in ["telco", "energy", "insurance"]:
        r = compare.compare(vertical, {"household": {}, "currentSubscriptions": []}, prefs(vertical), cat)
        assert r["currentMonthlyEur"] == 0.0


# --------------------------------------------------------------------------- #
# B1 == B2 numbers; reasons sumnik-free
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("vertical", ["telco", "energy", "insurance"])
def test_b1_equals_b2_numbers(cat, state, vertical):
    b1 = compare.compare(vertical, state, prefs(vertical), cat)
    b2 = reasons.explain(b1)
    assert _strip_why(b1) == _strip_why(b2)
    assert '"why"' not in json.dumps(b1)


def test_b2_adds_why(cat, state):
    b2 = reasons.explain(compare.compare("telco", state, prefs("telco"), cat))
    assert b2["dontPayFor"][0]["why"]
    assert b2["recommendation"]["mobile"]["why"]


@pytest.mark.parametrize("vertical", ["telco", "energy", "insurance"])
def test_reasons_have_no_sumniki(cat, state, vertical):
    b2 = reasons.explain(compare.compare(vertical, state, prefs(vertical), cat))
    for text in _iter_strings(b2):
        assert not (set(text) & SUMNIKI), "sumnik in: %r" % text


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


def test_http_state_has_household_and_kind_no_spoilers(client):
    s = client.get("/api/state").json()
    assert s["persona"]["name"] == "Marko Novak"
    assert s["household"]["homeOwnership"] == "tenant"
    tele = [l for l in s["currentSubscriptions"] if l["vertical"] == "telco"]
    assert {l["kind"] for l in tele} == {"fixed", "tv_addon", "mobile"}
    water = [l for l in s["currentSubscriptions"] if l["vertical"] == "water"][0]
    assert water["switchable"] is False
    dump = json.dumps(s)
    assert "GOTCHA" not in dump and "grounding" not in dump


def test_http_profile_defaults_to_canned(client):
    r = client.post("/api/profile?vertical=telco").json()
    assert r["profile"]["vertical"] == "telco"
    assert r["offer"]["monthlySavingsEur"] == 24.99
    assert r["offer"]["recommendation"]["mobile"]["why"]


def test_http_compare_b1_vs_b2(client, demo):
    body = {"state": demo, "preferences": prefs("telco")}
    b2 = client.post("/api/compare/telco", json=body).json()
    b1 = client.post("/api/compare/telco?explain=false", json=body).json()
    assert b2["monthlySavingsEur"] == b1["monthlySavingsEur"] == 24.99
    assert '"why"' in json.dumps(b2)
    assert '"why"' not in json.dumps(b1)


def test_http_unknown_vertical_404(client):
    assert client.post("/api/compare/water", json={}).status_code == 404


def test_http_compare_all_skips_water(client, demo):
    body = {"state": demo, "preferences": {v: prefs(v) for v in ["telco", "energy", "insurance"]}}
    r = client.post("/api/compare-all", json=body).json()
    assert set(r["byVertical"]) == {"telco", "energy", "insurance"}
    assert r["totals"]["skipped"] == ["water"]
    assert r["totals"]["monthlySavingsEur"] == 59.99  # telco 24.99 + insurance 35
    assert r["totals"]["currentMonthlyEur"] == 190.87  # excludes water's 22
