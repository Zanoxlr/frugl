"""FastAPI surface for the price-comparison calculator.

Stateless: every request carries its own `state` + `preferences`, so nothing here
touches prod, secrets, or an LLM. The engine (compare) produces B1 numbers; the
reasons layer adds B2 "why" strings unless ?explain=false.

Data model:
  state       = { persona, household, currentSubscriptions[], totals }   (GET /api/state)
  preferences = { vertical, signals, ... }                               (extraction output)

Endpoints:
  GET  /api/demo-user            -> the raw Marko persona file
  GET  /api/state                -> dashboard state (persona, household, current lines, totals)
  POST /api/compare/{vertical}   -> compare one vertical {state, preferences}
  POST /api/compare-all          -> compare telco+energy+insurance (water skipped)
  POST /api/profile              -> extraction stub -> { profile, offer }
"""

import json
import os

from fastapi import Body, FastAPI, HTTPException, Query

from . import catalog as catalog_module
from . import compare as compare_module
from . import reasons as reasons_module

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
VERTICALS = ("telco", "energy", "insurance")  # water is info-only, no endpoint

app = FastAPI(title="Frugl calculator API", version="0.2.0")

_CATALOG = catalog_module.load()  # static grounding data, load once


def _demo_user():
    with open(os.path.join(DATA_DIR, "demo_user.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _demo_preferences():
    with open(os.path.join(DATA_DIR, "demo_preferences.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _demo_state():
    """Build the state object the engine consumes from the persona file."""
    demo = _demo_user()
    return {
        "persona": demo.get("persona", {}),
        "household": demo.get("household", {}),
        "currentSubscriptions": demo.get("currentSubscriptions", []),
        "totals": demo.get("totals", {}),
    }


def _run(vertical, state, preferences, explain):
    result = compare_module.compare(vertical, state, preferences, _CATALOG)
    return reasons_module.explain(result) if explain else result


@app.get("/api/demo-user")
def get_demo_user():
    return _demo_user()


@app.get("/api/state")
def get_state():
    """Dashboard state: persona, shared household facts, current lines, totals.
    Trimmed of the demo-rigging notes/flags so the reveal comes from /api/profile.
    `switchable` is false for water (info-only municipal monopoly)."""
    demo = _demo_user()
    persona = demo.get("persona", {})
    lines = [
        {
            "vertical": s.get("vertical"),
            "kind": s.get("kind"),
            "provider": s.get("provider"),
            "planName": s.get("planName"),
            "monthlyEur": s.get("monthlyEur"),
            "attributes": s.get("attributes", {}),
            "switchable": s.get("vertical") != "water",
        }
        for s in demo.get("currentSubscriptions", [])
    ]
    return {
        "persona": {
            "name": persona.get("name"),
            "city": persona.get("city"),
            "household": persona.get("household"),
        },
        "household": demo.get("household", {}),
        "currentSubscriptions": lines,
        "totals": demo.get("totals", {}),
    }


@app.post("/api/compare/{vertical}")
def compare_vertical(
    vertical: str,
    payload: dict = Body(...),
    explain: bool = Query(True, description="B2 why strings; false = bare B1 numbers"),
):
    if vertical not in VERTICALS:
        raise HTTPException(status_code=404, detail="unknown vertical: %s" % vertical)
    return _run(vertical, payload.get("state"), payload.get("preferences"), explain)


@app.post("/api/compare-all")
def compare_all(
    payload: dict = Body(...),
    explain: bool = Query(True),
):
    """`state` carries all current lines; `preferences` maps vertical -> Preferences.
    Water lines are ignored."""
    state = payload.get("state") or {}
    prefs_by_vertical = payload.get("preferences") or {}

    results = {}
    total_current = 0.0
    total_savings = 0.0
    for vertical in VERTICALS:
        result = _run(vertical, state, prefs_by_vertical.get(vertical, {}), explain)
        results[vertical] = result
        total_current += result["currentMonthlyEur"] or 0.0
        total_savings += result["monthlySavingsEur"] or 0.0

    return {
        "byVertical": results,
        "totals": {
            "currentMonthlyEur": round(total_current, 2),
            "monthlySavingsEur": round(total_savings, 2),
            "annualSavingsEur": round(total_savings * 12, 2),
            "skipped": ["water"],
        },
    }


@app.post("/api/profile")
def build_profile(
    vertical: str = Query(None, description="required when not in the body"),
    payload: dict = Body(default={}),
    explain: bool = Query(True),
):
    """Extraction -> right-fit offer. Extraction from `history` is not wired yet, so
    the preferences fall back to the canned demo profile and `state` to the persona.
    Contract stays { profile, offer } when extraction lands."""
    vertical = vertical or payload.get("vertical")
    if vertical not in VERTICALS:
        raise HTTPException(status_code=404, detail="unknown vertical: %s" % vertical)

    preferences = payload.get("preferences") or _demo_preferences().get(vertical, {})
    state = payload.get("state") or _demo_state()

    offer = _run(vertical, state, preferences, explain)
    return {"profile": preferences, "offer": offer}
