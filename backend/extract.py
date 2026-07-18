"""Turn a chat transcript into a structured `Preferences` object via `claude -p`.

This is the extraction boundary in front of compare(): the LLM is free-form, so its
output is treated as HOSTILE input. Every signal is coerced to the exact type the
calculator expects, and anything mistyped is DROPPED (becomes absent -> compare reads
it as None = "unknown"), never passed through. A mistyped-but-parseable value is the
dangerous case (a string where a list is expected silently 500s the engine), so the
whitelist below is the real defense; compare.py keeps matching guards as depth.

Any failure at all (LLM error, non-JSON, not-an-object) -> a neutral fallback with
`degraded: True` so the caller can make a dead-LLM VISIBLE instead of silently serving
the floor-plan recommendation that empty signals happen to produce.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import llm as llm_module

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

with open(os.path.join(PROMPTS_DIR, "profile_extraction.md"), encoding="utf-8") as _fh:
    _PROMPT_TEMPLATE = _fh.read()

VERTICALS = ("telco", "energy", "insurance")

# Per-vertical signal whitelist: field -> kind. Anything not listed is discarded.
#   bool    -> real bool, or "true"/"false" string; else drop
#   num     -> int/float (not bool), or numeric string; else drop
#   str     -> non-empty string; else drop
#   str_num -> string OR number kept as-is (dataNeedGB: compare handles both); else drop
#   list    -> list, items coerced to lowercase strings; else drop
#   dict:<sub-keys> -> dict, listed sub-keys coerced to bool, others dropped; else drop
_SIGNAL_SPEC = {
    "telco": {
        "dataNeedGB": "str_num",
        "watchesSport": "bool",
        "paidTvPacksUsed": "list",
        "wantsFixedBroadband": "bool",
        "openToSwitchOperator": "bool",
        "travelsOutsideEU": "bool",
        "budgetPriority": "bool",
    },
    "energy": {
        "annualKwh": "num",
        "meterType": "str",
        "hasGas": "bool",
        "annualGasKwh": "num",
        "dayNightSplit": "str",
        "priceCertaintyPref": "str",
        "contractLockTolerance": "str",
        "eInvoiceOk": "bool",
    },
    "insurance": {
        "healthPrefs": "dict:valuesFasterPrivateAccess,expectsDentalWork",
        "floodExposed": "bool",
        "travelFrequency": "str",
        "coverElsewhere": "dict:personalAccident,roadsideAssist",
    },
}


def _degraded(vertical: str) -> dict:
    """Neutral, calculator-safe fallback. `degraded` lets the caller flag a dead LLM."""
    return {"vertical": vertical, "signals": {}, "summary": "", "dontNeed": [], "degraded": True}


def _clean_turn(text: Any) -> str:
    """Flatten control chars to spaces (same discipline as the chat prompt) so a pasted
    bill can't forge structure inside the transcript we hand the extractor."""
    return "".join(ch if ch >= " " else " " for ch in str(text)).strip()


def _render_transcript(history) -> str:
    rows = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        if role not in ("user", "assistant"):
            continue
        # Frontend HISTORY items carry `content`; older/backend callers use `text`.
        raw = turn.get("text")
        if raw is None:
            raw = turn.get("content")
        label = "Uporabnik" if role == "user" else "Svetovalec"
        rows.append("%s: %s" % (label, _clean_turn(raw if raw is not None else "")))
    return "\n".join(rows) if rows else "(prazen pogovor)"


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "da", "yes"):
            return True
        if low in ("false", "ne", "no"):
            return False
    return None


def _as_num(value: Any):
    if isinstance(value, bool):
        return None  # bool is an int subclass; never a usage number
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce(kind: str, value: Any):
    """Return the coerced value, or the sentinel `_DROP` when it can't be trusted.
    `None` (the model saying "unknown") is preserved verbatim for every kind."""
    if value is None:
        return None
    if kind == "bool":
        b = _as_bool(value)
        return b if b is not None else _DROP
    if kind == "num":
        n = _as_num(value)
        return n if n is not None else _DROP
    if kind == "str":
        return value if isinstance(value, str) and value.strip() else _DROP
    if kind == "str_num":
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        return _DROP
    if kind == "list":
        if not isinstance(value, list):
            return _DROP  # a bare string here is the silent-garbage bug: drop it
        return [str(item).strip().lower() for item in value if item is not None]
    if kind.startswith("dict:"):
        if not isinstance(value, dict):
            return _DROP
        sub_keys = kind.split(":", 1)[1].split(",")
        out = {}
        for k in sub_keys:
            if k in value:
                b = _as_bool(value[k])
                out[k] = b  # bool or None; a mistyped sub-value collapses to None (unknown)
        return out
    return _DROP


_DROP = object()


def _coerce_signals(vertical: str, raw_signals: Any) -> dict:
    spec = _SIGNAL_SPEC[vertical]
    if not isinstance(raw_signals, dict):
        return {}
    out = {}
    for field, kind in spec.items():
        if field not in raw_signals:
            continue
        coerced = _coerce(kind, raw_signals[field])
        if coerced is _DROP:
            continue
        out[field] = coerced
    return out


def _strip_fences(text: str) -> str:
    """Drop a leading/trailing ```...``` fence if the model wrapped the JSON despite the
    prompt forbidding it."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _string_list(value: Any) -> list:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def extract_preferences(vertical: str, history, *, timeout: int = 30) -> dict:
    """Extract a `Preferences` object for `vertical` from a chat `history`.

    Returns { vertical, signals, summary, dontNeed, context?, degraded }. On ANY failure
    returns the degraded fallback. The output `vertical` is always forced to the caller's
    requested one — the calculator is invoked per-vertical, so the model's guess never
    overrides it.
    """
    if vertical not in VERTICALS:
        return _degraded(vertical)

    prompt = _PROMPT_TEMPLATE.replace("{{CONVERSATION}}", _render_transcript(history))

    try:
        raw = llm_module.ask(prompt, timeout=timeout)  # default (strong) model
    except llm_module.LlmError:
        return _degraded(vertical)

    try:
        parsed = json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, ValueError):
        return _degraded(vertical)

    if not isinstance(parsed, dict):
        return _degraded(vertical)

    summary = parsed.get("summary")
    result = {
        "vertical": vertical,  # forced: never trust the model's vertical over the caller's
        "signals": _coerce_signals(vertical, parsed.get("signals")),
        "summary": summary if isinstance(summary, str) else "",
        "dontNeed": _string_list(parsed.get("dontNeed")),
        "degraded": False,
    }
    context = _string_list(parsed.get("context"))
    if context:
        result["context"] = context
    return result
