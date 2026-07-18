"""Extraction boundary: the LLM output is treated as hostile. These cover type
coercion (keep valid, drop mistyped, preserve null=unknown), the degraded fallback on
every failure mode, fence stripping, forced vertical, and the content||text transcript
key. `llm.ask` is always mocked — no real `claude -p`.
"""
import json

import pytest

import backend.extract as extract
import backend.llm as llm


def _mock_ask(monkeypatch, ret=None, raise_error=False):
    def fake(prompt, *, timeout=30, model=None):
        if raise_error:
            raise llm.LlmError("boom")
        return ret
    monkeypatch.setattr(llm, "ask", fake)


def test_valid_telco_signals_pass_through(monkeypatch):
    _mock_ask(monkeypatch, ret=json.dumps({
        "vertical": "telco",
        "summary": "gleda serije, sporta ne",
        "dontNeed": ["sportni paket"],
        "signals": {
            "dataNeedGB": "mid", "watchesSport": False, "paidTvPacksUsed": ["movies"],
            "wantsFixedBroadband": True, "openToSwitchOperator": True,
            "travelsOutsideEU": False, "budgetPriority": True,
        },
    }))
    out = extract.extract_preferences("telco", [{"role": "user", "content": "hi"}])
    assert out["degraded"] is False
    assert out["vertical"] == "telco"
    assert out["signals"]["dataNeedGB"] == "mid"
    assert out["signals"]["watchesSport"] is False
    assert out["signals"]["paidTvPacksUsed"] == ["movies"]
    assert out["summary"] == "gleda serije, sporta ne"
    assert out["dontNeed"] == ["sportni paket"]


def test_mistyped_signals_are_dropped_not_passed(monkeypatch):
    # paidTvPacksUsed as a bare string is the silent-garbage bug: MUST be dropped.
    _mock_ask(monkeypatch, ret=json.dumps({
        "vertical": "telco",
        "signals": {
            "paidTvPacksUsed": "sport",   # string, not list -> drop
            "watchesSport": "true",       # string bool -> coerce True
            "dataNeedGB": 15,             # number is fine for str_num -> keep
            "budgetPriority": 1,          # int, not bool -> drop (strict)
            "openToSwitchOperator": None, # null -> preserved as unknown
        },
    }))
    sig = extract.extract_preferences("telco", [{"role": "user", "content": "x"}])["signals"]
    assert "paidTvPacksUsed" not in sig
    assert sig["watchesSport"] is True
    assert sig["dataNeedGB"] == 15
    assert "budgetPriority" not in sig
    assert sig["openToSwitchOperator"] is None


def test_nested_dict_signal_coercion(monkeypatch):
    _mock_ask(monkeypatch, ret=json.dumps({
        "vertical": "insurance",
        "signals": {
            "healthPrefs": {"valuesFasterPrivateAccess": True, "expectsDentalWork": "nope"},
            "coverElsewhere": "yes",  # not a dict -> drop entirely
            "floodExposed": False,
        },
    }))
    sig = extract.extract_preferences("insurance", [{"role": "user", "content": "x"}])["signals"]
    assert sig["healthPrefs"]["valuesFasterPrivateAccess"] is True
    assert sig["healthPrefs"]["expectsDentalWork"] is None  # unparseable bool -> unknown
    assert "coverElsewhere" not in sig
    assert sig["floodExposed"] is False


def test_llm_error_returns_degraded(monkeypatch):
    _mock_ask(monkeypatch, raise_error=True)
    out = extract.extract_preferences("telco", [{"role": "user", "content": "x"}])
    assert out == {"vertical": "telco", "signals": {}, "summary": "", "dontNeed": [], "degraded": True}


def test_non_json_returns_degraded(monkeypatch):
    _mock_ask(monkeypatch, ret="oprosti, ne morem")
    assert extract.extract_preferences("telco", [{"role": "user", "content": "x"}])["degraded"] is True


def test_json_array_not_object_returns_degraded(monkeypatch):
    _mock_ask(monkeypatch, ret="[1,2,3]")
    assert extract.extract_preferences("energy", [{"role": "user", "content": "x"}])["degraded"] is True


def test_code_fence_is_stripped(monkeypatch):
    _mock_ask(monkeypatch, ret='```json\n{"vertical":"telco","signals":{"watchesSport":true}}\n```')
    out = extract.extract_preferences("telco", [{"role": "user", "content": "x"}])
    assert out["degraded"] is False and out["signals"]["watchesSport"] is True


def test_vertical_is_forced_to_caller(monkeypatch):
    # Model claims energy; caller asked telco -> output vertical stays telco.
    _mock_ask(monkeypatch, ret=json.dumps({"vertical": "energy", "signals": {}}))
    assert extract.extract_preferences("telco", [{"role": "user", "content": "x"}])["vertical"] == "telco"


def test_transcript_reads_content_and_text_keys(monkeypatch):
    seen = {}

    def fake(prompt, *, timeout=30, model=None):
        seen["prompt"] = prompt
        return json.dumps({"vertical": "telco", "signals": {}})

    monkeypatch.setattr(llm, "ask", fake)
    extract.extract_preferences("telco", [
        {"role": "user", "content": "iz contenta"},
        {"role": "assistant", "text": "iz texta"},
    ])
    assert "iz contenta" in seen["prompt"] and "iz texta" in seen["prompt"]


def test_unknown_vertical_returns_degraded(monkeypatch):
    _mock_ask(monkeypatch, ret=json.dumps({"vertical": "water", "signals": {}}))
    assert extract.extract_preferences("water", [{"role": "user", "content": "x"}])["degraded"] is True
