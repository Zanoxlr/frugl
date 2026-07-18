"""Endpoint-level coverage for the demo loop: /api/profile from real history, /api/lead
capture-to-file, the demo gate's fail-closed paths, and the compare hardening (a mistyped
signal must not 500). `llm.ask` is mocked; the gate env is set per-test via monkeypatch.
"""
import json

import pytest
from fastapi.testclient import TestClient

import backend.llm as llm
import backend.main as main


@pytest.fixture
def client():
    return TestClient(main.app)


def _mock_ask(monkeypatch, ret=None, raise_error=False):
    def fake(prompt, *, timeout=30, model=None):
        if raise_error:
            raise llm.LlmError("boom")
        return ret
    monkeypatch.setattr(llm, "ask", fake)


# --------------------------------------------------------------------------- #
# /api/profile — extraction from history feeds the offer
# --------------------------------------------------------------------------- #
def test_profile_from_history_uses_extracted_prefs(client, monkeypatch):
    _mock_ask(monkeypatch, ret=json.dumps({
        "vertical": "telco", "summary": "sporta ne gleda",
        "signals": {"watchesSport": False, "paidTvPacksUsed": []},
    }))
    r = client.post("/api/profile?vertical=telco", json={"history": [{"role": "user", "content": "ne gledam sporta"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is False
    assert body["profile"]["summary"] == "sporta ne gleda"
    assert "offer" in body and body["offer"]["vertical"] == "telco"


def test_profile_degraded_when_extraction_fails(client, monkeypatch):
    _mock_ask(monkeypatch, raise_error=True)
    r = client.post("/api/profile?vertical=telco", json={"history": [{"role": "user", "content": "x"}]})
    assert r.status_code == 200 and r.json()["degraded"] is True


def test_profile_without_history_is_canned_not_degraded(client):
    r = client.post("/api/profile?vertical=insurance", json={})
    assert r.status_code == 200 and r.json()["degraded"] is False


# --------------------------------------------------------------------------- #
# /api/lead — writes one record to the env-overridable leads path
# --------------------------------------------------------------------------- #
def test_lead_writes_record(client, monkeypatch, tmp_path):
    leads = tmp_path / "leads.jsonl"
    monkeypatch.setattr(main, "LEADS_PATH", str(leads))
    _mock_ask(monkeypatch, ret=json.dumps({"vertical": "telco", "signals": {"watchesSport": False}}))

    r = client.post("/api/lead?vertical=telco", json={"history": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["degraded"] is False and body["leadId"]

    lines = leads.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["id"] == body["leadId"]
    assert rec["vertical"] == "telco"
    assert "profile" in rec and "offer" in rec and "createdAt" in rec


def test_lead_appends_not_overwrites(client, monkeypatch, tmp_path):
    leads = tmp_path / "leads.jsonl"
    monkeypatch.setattr(main, "LEADS_PATH", str(leads))
    client.post("/api/lead?vertical=telco", json={})
    client.post("/api/lead?vertical=energy", json={})
    assert len(leads.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_lead_unknown_vertical_404(client):
    assert client.post("/api/lead?vertical=water", json={}).status_code == 404


# --------------------------------------------------------------------------- #
# Demo gate — armed => fail closed on every misconfiguration
# --------------------------------------------------------------------------- #
FUTURE = "2999-01-01T00:00:00+00:00"
PAST = "2000-01-01T00:00:00Z"


def _arm(monkeypatch, expires=FUTURE):
    monkeypatch.setenv("FRUGL_DEMO_GATE", "1")
    if expires is not None:
        monkeypatch.setenv("FRUGL_DEMO_EXPIRES", expires)
    else:
        monkeypatch.delenv("FRUGL_DEMO_EXPIRES", raising=False)


def test_gate_disarmed_is_open(client, monkeypatch):
    monkeypatch.delenv("FRUGL_DEMO_GATE", raising=False)
    assert client.get("/api/state").status_code == 200


def test_gate_armed_before_expiry_is_open_no_key(client, monkeypatch):
    # Expiry-only gate: while live, the demo is open to anyone — no key needed.
    _arm(monkeypatch)
    assert client.get("/api/state").status_code == 200


def test_gate_armed_expiry_unset_403(client, monkeypatch):
    _arm(monkeypatch, expires=None)
    assert client.get("/api/state").status_code == 403


def test_gate_armed_expired_403(client, monkeypatch):
    _arm(monkeypatch, expires=PAST)
    assert client.get("/api/state").status_code == 403


def test_gate_armed_bad_expiry_403(client, monkeypatch):
    _arm(monkeypatch, expires="not-a-date")
    assert client.get("/api/state").status_code == 403


def test_health_open_even_when_armed(client, monkeypatch):
    _arm(monkeypatch)
    assert client.get("/api/health").status_code == 200


# --------------------------------------------------------------------------- #
# compare hardening — a mistyped signal must not 500
# --------------------------------------------------------------------------- #
def test_compare_mistyped_signal_no_500(client):
    r = client.post("/api/compare/telco", json={
        "state": {"currentSubscriptions": []},
        "preferences": {"vertical": "telco", "signals": {"paidTvPacksUsed": "sport"}},
    })
    assert r.status_code == 200 and r.json()["vertical"] == "telco"


def test_compare_signals_as_list_no_500(client):
    r = client.post("/api/compare/insurance", json={
        "state": {"currentSubscriptions": []},
        "preferences": {"vertical": "insurance", "signals": ["not", "a", "dict"]},
    })
    assert r.status_code == 200 and r.json()["vertical"] == "insurance"
