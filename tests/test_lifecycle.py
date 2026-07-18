"""Unit tests for backend/lifecycle.py — contract lifecycle status derivation.

Pure + deterministic: every test pins `as_of` so nothing depends on the real calendar.
Also asserts the Marko seed produces exactly one renewal on the documented demo date.
"""

import json
import os
from datetime import date

import pytest

from backend import lifecycle as lc

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")

# documented demo anchor: on this date the telco-fixed line sits in its renewal window
DEMO_ASOF = "2026-07-23"


@pytest.fixture(scope="module")
def demo_subs():
    with open(os.path.join(ROOT, "data", "demo_user.json"), encoding="utf-8") as fh:
        return json.load(fh)["currentSubscriptions"]


# --- no_contract: no lock, missing/blank contract ----------------------------

def test_none_contract_is_no_contract():
    out = lc.lifecycle(None, as_of="2026-07-23")
    assert out["status"] == lc.NO_CONTRACT
    assert out["daysRemaining"] is None
    assert out["actionRequired"] is False


def test_term_null_is_no_contract():
    out = lc.lifecycle({"termMonths": None, "autoRenews": True}, as_of="2026-07-23")
    assert out["status"] == lc.NO_CONTRACT
    assert out["autoRenews"] is True


def test_term_present_but_no_derivable_end_is_no_contract():
    # termMonths set but no startDate and no endDate -> can't place it -> no_contract
    out = lc.lifecycle({"termMonths": 24}, as_of="2026-07-23")
    assert out["status"] == lc.NO_CONTRACT


# --- active / renewal_window / expired ---------------------------------------

def test_active_when_far_from_end():
    c = {"endDate": "2027-02-01", "termMonths": 24, "noticePeriodDays": 30}
    out = lc.lifecycle(c, as_of=DEMO_ASOF)
    assert out["status"] == lc.ACTIVE
    assert out["actionRequired"] is False
    assert out["daysRemaining"] > 44


def test_renewal_window_opens_with_runway_before_notice_deadline():
    # end 2026-09-01, notice 30d -> deadline 2026-08-02, window = max(30, 44) = 44 days.
    # as_of 2026-07-23 -> 40 days out -> in window, and 10 days left to cancel.
    c = {"startDate": "2024-09-01", "termMonths": 24, "endDate": "2026-09-01", "noticePeriodDays": 30}
    out = lc.lifecycle(c, as_of=DEMO_ASOF)
    assert out["status"] == lc.RENEWAL_WINDOW
    assert out["daysRemaining"] == 40
    assert out["noticeDeadline"] == "2026-08-02"
    assert out["daysToNoticeDeadline"] == 10
    assert out["actionRequired"] is True


def test_expired_line():
    c = {"endDate": "2026-01-01", "termMonths": 12, "noticePeriodDays": 30, "autoRenews": True}
    out = lc.lifecycle(c, as_of=DEMO_ASOF)
    assert out["status"] == lc.EXPIRED
    assert out["daysRemaining"] < 0
    assert out["actionRequired"] is True  # auto-renewed, still worth acting


def test_boundary_exactly_at_window_edge_is_renewal_window():
    # window for a 30-day-notice contract is 44 days; exactly 44 days out is still "in".
    c = {"endDate": "2026-09-01", "termMonths": 24, "noticePeriodDays": 30}
    out = lc.lifecycle(c, as_of="2026-07-19")  # 2026-09-01 - 44 days
    assert out["daysRemaining"] == 44
    assert out["status"] == lc.RENEWAL_WINDOW


# --- end-date derivation ------------------------------------------------------

def test_end_date_derived_from_start_plus_term():
    out = lc.lifecycle({"startDate": "2025-02-01", "termMonths": 24, "noticePeriodDays": 30}, as_of=DEMO_ASOF)
    assert out["endDate"] == "2027-02-01"


def test_month_add_clamps_day_end_of_month():
    # Jan 31 + 1 month must clamp to Feb 28 (2026 not a leap year), not overflow to March.
    out = lc.lifecycle({"startDate": "2026-01-31", "termMonths": 1}, as_of="2026-01-01")
    assert out["endDate"] == "2026-02-28"


# --- injectable "today" -------------------------------------------------------

def test_env_override_used_when_no_arg(monkeypatch):
    monkeypatch.setenv("FRUGL_DEMO_TODAY", "2026-07-23")
    c = {"endDate": "2026-09-01", "termMonths": 24, "noticePeriodDays": 30}
    assert lc.lifecycle(c)["status"] == lc.RENEWAL_WINDOW


def test_explicit_arg_beats_env(monkeypatch):
    monkeypatch.setenv("FRUGL_DEMO_TODAY", "2020-01-01")
    c = {"endDate": "2026-09-01", "termMonths": 24, "noticePeriodDays": 30}
    # explicit as_of wins over the (far-past) env value
    assert lc.lifecycle(c, as_of="2026-07-23")["status"] == lc.RENEWAL_WINDOW


def test_resolve_today_real_date_fallback(monkeypatch):
    monkeypatch.delenv("FRUGL_DEMO_TODAY", raising=False)
    assert lc.resolve_today() == date.today()


# --- robustness: never raise on bad data -------------------------------------

def test_malformed_date_degrades_to_no_contract():
    out = lc.lifecycle({"endDate": "not-a-date", "termMonths": 12}, as_of=DEMO_ASOF)
    assert out["status"] == lc.NO_CONTRACT


def test_unparseable_as_of_falls_back_to_real_today(monkeypatch):
    monkeypatch.delenv("FRUGL_DEMO_TODAY", raising=False)
    # garbage as_of must not crash; it falls through to real today
    out = lc.lifecycle({"endDate": "2027-02-01", "termMonths": 24}, as_of="garbage")
    assert out["status"] in (lc.ACTIVE, lc.RENEWAL_WINDOW, lc.EXPIRED)


# --- helpers ------------------------------------------------------------------

def test_annotate_subscriptions_is_non_mutating(demo_subs):
    annotated = lc.annotate_subscriptions(demo_subs, as_of=DEMO_ASOF)
    assert all("lifecycle" in line for line in annotated)
    assert all("lifecycle" not in line for line in demo_subs)  # originals untouched


def test_due_for_renewal_pairs_line_with_lifecycle(demo_subs):
    due = lc.due_for_renewal(demo_subs, as_of=DEMO_ASOF)
    assert {d["line"]["lineId"] for d in due} == {"telco-fixed-a1-xplore"}
    assert due[0]["lifecycle"]["status"] == lc.RENEWAL_WINDOW


# --- the seed on the demo date: exactly one renewal --------------------------

def test_demo_seed_states_on_demo_date(demo_subs):
    by_id = {s["lineId"]: lc.lifecycle(s.get("contract"), as_of=DEMO_ASOF) for s in demo_subs}
    assert by_id["telco-fixed-a1-xplore"]["status"] == lc.RENEWAL_WINDOW
    assert by_id["telco-mobile-maksimio"]["status"] == lc.ACTIVE
    assert by_id["ins-health-vzajemna-dopolnilno"]["status"] == lc.ACTIVE
    assert by_id["ins-car-triglav-ao"]["status"] == lc.ACTIVE
    for no_lock in ("telco-addon-arena", "energy-elec-petrol-redni", "water-voka"):
        assert by_id[no_lock]["status"] == lc.NO_CONTRACT
    # exactly one line is in the renewal window
    assert sum(v["status"] == lc.RENEWAL_WINDOW for v in by_id.values()) == 1
