"""End-to-end tests for the price-comparison calculator.

Covers the three Marko happy paths, the edges the adversary pass flagged (energy
no-usage, insurance null-price, empty profiles, null min guards), the B1==B2
numbers invariant, the water skip, and the sumnik-free reasons copy.
"""

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


def needs(vertical):
    with open(os.path.join(FIXTURES, "marko_%s.needs.json" % vertical), encoding="utf-8") as fh:
        return json.load(fh)


def current(demo, vertical):
    return [s for s in demo["currentSubscriptions"] if s["vertical"] == vertical]


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
    """Deep copy with every `why` key removed, so B1/B2 numbers can be compared."""
    if isinstance(obj, dict):
        return {k: _strip_why(v) for k, v in obj.items() if k != "why"}
    if isinstance(obj, list):
        return [_strip_why(v) for v in obj]
    return obj


# --------------------------------------------------------------------------- #
# Catalog conformance
# --------------------------------------------------------------------------- #
def test_catalog_counts_nonzero():
    counts = catalog.load_counts()
    assert counts["mobilePlans"] > 0
    assert counts["tvAddons"] > 0
    assert counts["electricity"] > 0
    assert counts["ozpMonthlyEur"] == 39.36


def test_mvno_dedup_and_full_speed(cat):
    plans = cat["telco"]["mobilePlans"]
    # BOB comes only from telco_mvno.json (has zeleni), never the stale rows.
    bob = [p for p in plans if p["operator"] == "BOB"]
    assert any(p["name"] == "zeleni bob" for p in bob)
    assert all(p["source"] == "telco_mvno" for p in bob)
    zeleni = next(p for p in bob if p["name"] == "zeleni bob")
    assert zeleni["fullSpeedGB"] == 20.0  # the load-bearing number
    rdeci = next(p for p in bob if p["name"] == "rdeci bob")
    assert rdeci["fullSpeedGB"] == 10.0  # excluded at need=15, must stay 10


# --------------------------------------------------------------------------- #
# Telco happy path (the headline DoD)
# --------------------------------------------------------------------------- #
def test_telco_marko_saves_24_99(cat, demo):
    r = compare.compare("telco", current(demo, "telco"), needs("telco"), cat)
    assert r["currentMonthlyEur"] == 88.97
    assert r["monthlySavingsEur"] == 24.99
    assert r["annualSavingsEur"] == 299.88
    # Arena dropped
    assert any(d["ruleCode"] == "TELCO_UNUSED_SPORT_ADDON" for d in r["dontPayFor"])
    # Mobile swapped to zeleni bob
    mob = r["recommendation"]["mobile"]
    assert mob["toName"] == "zeleni bob" and mob["toMonthlyEur"] == 7.99


def test_telco_threshold_excludes_cheaper_but_too_small(cat, demo):
    # rdeci bob (5.99, fs=10) is cheaper than zeleni but below the 15 GB need,
    # so it must NOT be the recommendation.
    r = compare.compare("telco", current(demo, "telco"), needs("telco"), cat)
    assert r["recommendation"]["mobile"]["toName"] != "rdeci bob"


def test_telco_watches_sport_keeps_arena(cat, demo):
    n = needs("telco")
    n["telco"]["watchesSport"] = True
    r = compare.compare("telco", current(demo, "telco"), n, cat)
    assert all(d["ruleCode"] != "TELCO_UNUSED_SPORT_ADDON" for d in r["dontPayFor"])
    # Only the mobile saving remains (27.99 -> 7.99 = 20.00).
    assert r["monthlySavingsEur"] == 20.0


# --------------------------------------------------------------------------- #
# Energy: no-usage trade-off, null savings
# --------------------------------------------------------------------------- #
def test_energy_no_usage_null_savings(cat, demo):
    r = compare.compare("energy", current(demo, "energy"), needs("energy"), cat)
    assert r["currentMonthlyEur"] == 41.9  # pass-through, never recomputed
    assert r["monthlySavingsEur"] is None
    assert r["annualSavingsEur"] is None  # null, not 0
    assert r["recommendedMonthlyEur"] is None
    trade = r["recommendation"]["tradeoff"]
    # The zero-fixed-fee option and the lowest-unit option genuinely differ.
    assert trade["lowestFixedFee"]["fixedMonthlyEur"] == 0
    assert trade["lowestFixedFee"]["name"] != trade["lowestUnitPrice"]["name"]


def test_energy_known_usage_ranks(cat, demo):
    n = needs("energy")
    n["energy"]["annualKwh"] = 3000
    r = compare.compare("energy", current(demo, "energy"), n, cat)
    assert r["recommendation"]["ruleCode"] == "ENERGY_RANKED_BY_USAGE"
    assert r["recommendation"]["estimatedAnnualEnergyEur"] > 0
    assert r["monthlySavingsEur"] is None  # all-in current can't be decomposed


# --------------------------------------------------------------------------- #
# Insurance: null price, biggest single reveal
# --------------------------------------------------------------------------- #
def test_insurance_legacy_dopolnilno_droppable(cat, demo):
    r = compare.compare("insurance", current(demo, "insurance"), needs("insurance"), cat)
    assert r["currentMonthlyEur"] == 60.0
    assert r["monthlySavingsEur"] == 35.0
    assert r["annualSavingsEur"] == 420.0
    reveal = r["dontPayFor"][0]
    assert reveal["ruleCode"] == "INS_LEGACY_DOPOLNILNO"
    assert reveal["monthlyEur"] == 35.0  # falls back to the line's own price


def test_insurance_empty_profile_no_reveal_no_crash(cat, demo):
    # Empty needs: the paysLegacyDopolnilno flag is absent, so the 35 EUR reveal
    # must silently vanish and nothing may crash.
    r = compare.compare("insurance", current(demo, "insurance"), {}, cat)
    assert r["dontPayFor"] == []
    assert r["monthlySavingsEur"] is None
    assert r["annualSavingsEur"] is None


# --------------------------------------------------------------------------- #
# Robustness: null price lines must not crash any min()/sum()
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("vertical", ["telco", "energy", "insurance"])
def test_null_price_lines_dont_crash(cat, vertical):
    line = {"vertical": vertical, "provider": "X", "planName": "mystery", "monthlyEur": None}
    r = compare.compare(vertical, [line], needs(vertical), cat)
    assert r["currentMonthlyEur"] == 0.0


def test_empty_current_all_verticals(cat):
    for vertical in ["telco", "energy", "insurance"]:
        r = compare.compare(vertical, [], needs(vertical), cat)
        assert r["currentMonthlyEur"] == 0.0


# --------------------------------------------------------------------------- #
# B1 == B2 numbers; B2 adds only prose
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("vertical", ["telco", "energy", "insurance"])
def test_b1_equals_b2_numbers(cat, demo, vertical):
    b1 = compare.compare(vertical, current(demo, vertical), needs(vertical), cat)
    b2 = reasons.explain(b1)
    assert _strip_why(b1) == _strip_why(b2)
    # B1 carries no why anywhere.
    assert all(k != "why" for s in _iter_strings(b1) for k in [s]) or True
    b1_json = json.dumps(b1)
    assert '"why"' not in b1_json


def test_b2_adds_why(cat, demo):
    b2 = reasons.explain(compare.compare("telco", current(demo, "telco"), needs("telco"), cat))
    assert b2["dontPayFor"][0]["why"]
    assert b2["recommendation"]["mobile"]["why"]


# --------------------------------------------------------------------------- #
# Reasons copy must be sumnik-free
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("vertical", ["telco", "energy", "insurance"])
def test_reasons_have_no_sumniki(cat, demo, vertical):
    b2 = reasons.explain(compare.compare(vertical, current(demo, vertical), needs(vertical), cat))
    for text in _iter_strings(b2):
        assert not (set(text) & SUMNIKI), "sumnik in: %r" % text


# --------------------------------------------------------------------------- #
# HTTP surface + compare-all water skip
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.main import app

    return TestClient(app)


def test_http_compare_telco_b2_and_b1(client, demo):
    body = {"current": current(demo, "telco"), "needs": needs("telco")}
    b2 = client.post("/api/compare/telco", json=body).json()
    b1 = client.post("/api/compare/telco?explain=false", json=body).json()
    assert b2["monthlySavingsEur"] == b1["monthlySavingsEur"] == 24.99
    assert '"why"' in json.dumps(b2)
    assert '"why"' not in json.dumps(b1)


def test_http_unknown_vertical_404(client):
    assert client.post("/api/compare/water", json={}).status_code == 404


def test_http_state_shape_and_no_spoilers(client):
    s = client.get("/api/state").json()
    assert s["persona"]["name"] == "Marko Novak"
    assert s["totals"]["monthlyEur"] == 212.87
    water = [l for l in s["currentSubscriptions"] if l["vertical"] == "water"]
    assert water and water[0]["switchable"] is False
    assert all(l["switchable"] for l in s["currentSubscriptions"] if l["vertical"] != "water")
    # dashboard must not leak the demo-rigging notes/flags
    dump = json.dumps(s)
    assert "GOTCHA" not in dump and "flags" not in dump


def test_http_profile_defaults_to_canned(client):
    # No body: falls back to the canned Marko profile + persona lines.
    r = client.post("/api/profile?vertical=telco").json()
    assert r["profile"]["vertical"] == "telco"
    assert r["offer"]["monthlySavingsEur"] == 24.99
    assert r["offer"]["recommendation"]["mobile"]["why"]  # B2 by default


def test_http_profile_accepts_explicit_profile(client):
    body = {"vertical": "telco", "profile": needs("telco"), "current": None}
    r = client.post("/api/profile?explain=false", json=body).json()
    assert r["offer"]["monthlySavingsEur"] == 24.99
    assert '"why"' not in json.dumps(r["offer"])  # B1 bare


def test_http_profile_unknown_vertical_404(client):
    assert client.post("/api/profile?vertical=water").status_code == 404


def test_http_compare_all_skips_water(client, demo):
    body = {
        "current": demo["currentSubscriptions"],
        "needs": {v: needs(v) for v in ["telco", "energy", "insurance"]},
    }
    r = client.post("/api/compare-all", json=body).json()
    assert set(r["byVertical"]) == {"telco", "energy", "insurance"}
    assert "water" not in r["byVertical"]
    assert r["totals"]["skipped"] == ["water"]
    # telco 24.99 + insurance 35.0 (energy null -> 0)
    assert r["totals"]["monthlySavingsEur"] == 59.99
    assert r["totals"]["currentMonthlyEur"] == 190.87  # excludes water's 22
