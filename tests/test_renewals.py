"""Endpoint coverage for the renewals wiring: lifecycle on /api/state and the
/api/renewals feed. The demo gate is disarmed in the test env (FRUGL_DEMO_GATE unset),
so the client hits the routes directly. `as_of` is pinned so nothing depends on the clock.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

DEMO_ASOF = "2026-07-23"

OFFER_KEYS = {"vertical", "currentMonthlyEur", "recommendation", "recommendedMonthlyEur",
              "dontPayFor", "monthlySavingsEur", "annualSavingsEur", "notes"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# --- /api/state gains contract + lifecycle per line --------------------------

def test_state_lines_carry_lifecycle(client):
    state = client.get("/api/state", params={"as_of": DEMO_ASOF}).json()
    by_id = {ln["lineId"]: ln for ln in state["currentSubscriptions"]}
    assert by_id  # lineIds present
    assert all("lifecycle" in ln and "contract" in ln for ln in state["currentSubscriptions"])

    fiber = by_id["telco-fixed-a1-xplore"]
    assert fiber["lifecycle"]["status"] == "renewal_window"
    assert fiber["lifecycle"]["endDate"] == "2026-09-01"
    assert fiber["lifecycle"]["daysToNoticeDeadline"] == 10

    assert by_id["water-voka"]["lifecycle"]["status"] == "no_contract"
    assert by_id["telco-mobile-maksimio"]["lifecycle"]["status"] == "active"


# --- /api/renewals feed -------------------------------------------------------

def test_renewals_returns_the_one_due_line_with_an_offer(client):
    body = client.get("/api/renewals", params={"as_of": DEMO_ASOF}).json()
    assert body["asOf"] == DEMO_ASOF
    assert len(body["renewals"]) == 1

    r = body["renewals"][0]
    assert r["lineId"] == "telco-fixed-a1-xplore"
    assert r["vertical"] == "telco"
    assert r["current"]["monthlyEur"] == 55.99
    assert r["lifecycle"]["status"] == "renewal_window"
    assert OFFER_KEYS <= set(r["offer"])          # full compare()-shaped offer attached
    assert r["degraded"] is False


def test_renewals_empty_when_nothing_is_due(client):
    # far in the past: every contract is comfortably active -> no renewals
    body = client.get("/api/renewals", params={"as_of": "2024-01-01"}).json()
    assert body["renewals"] == []
    assert body["asOf"] == "2024-01-01"


def test_renewals_default_asof_uses_real_today(client):
    # no as_of arg: must not error and must echo a real ISO date
    body = client.get("/api/renewals").json()
    assert "asOf" in body and len(body["asOf"]) == 10
    assert isinstance(body["renewals"], list)
