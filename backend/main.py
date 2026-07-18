"""FastAPI surface for the price-comparison calculator.

Stateless: every request carries its own `current` + `needs`, so nothing here
touches prod, secrets, or an LLM. The engine (compare) produces B1 numbers; the
reasons layer adds B2 "why" strings unless ?explain=false.

Endpoints:
  GET  /api/demo-user            -> the Marko persona (data/demo_user.json)
  POST /api/compare/{vertical}   -> compare one vertical {current, needs}
  POST /api/compare-all          -> compare telco+energy+insurance (water skipped)
"""

import json
import os

from fastapi import Body, FastAPI, HTTPException, Query

from . import catalog as catalog_module
from . import compare as compare_module
from . import reasons as reasons_module

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
VERTICALS = ("telco", "energy", "insurance")  # water is info-only, no endpoint

app = FastAPI(title="Frugl calculator API", version="0.1.0")

# The catalog is static grounding data; load once at import.
_CATALOG = catalog_module.load()


def _demo_user():
    with open(os.path.join(DATA_DIR, "demo_user.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _demo_needs():
    with open(os.path.join(DATA_DIR, "demo_needs.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _demo_current(vertical):
    return [s for s in _demo_user()["currentSubscriptions"] if s.get("vertical") == vertical]


def _run(vertical, current, needs, explain):
    result = compare_module.compare(vertical, current, needs, _CATALOG)
    return reasons_module.explain(result) if explain else result


@app.get("/api/demo-user")
def get_demo_user():
    return _demo_user()


@app.get("/api/state")
def get_state():
    """Dashboard state: the persona, their current lines, and totals. Trimmed of the
    demo-rigging notes/flags so the reveal comes from /api/profile, not the dashboard.
    `switchable` is false for water (info-only municipal monopoly)."""
    demo = _demo_user()
    persona = demo.get("persona", {})
    lines = [
        {
            "vertical": s.get("vertical"),
            "provider": s.get("provider"),
            "planName": s.get("planName"),
            "monthlyEur": s.get("monthlyEur"),
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
        "currentSubscriptions": lines,
        "totals": demo.get("totals", {}),
    }


@app.post("/api/profile")
def build_profile(
    vertical: str = Query(None, description="required when not in the body"),
    payload: dict = Body(default={}),
    explain: bool = Query(True),
):
    """Extraction -> right-fit offer. Extraction from `history` is not wired yet, so
    the profile falls back to the canned demo profile for the vertical; `current`
    falls back to the persona's lines. Both become real once /api/chat + extraction
    land, with no contract change: response stays { profile, offer }."""
    vertical = vertical or payload.get("vertical")
    if vertical not in VERTICALS:
        raise HTTPException(status_code=404, detail="unknown vertical: %s" % vertical)

    profile = payload.get("profile") or _demo_needs().get(vertical, {})
    current = payload.get("current")
    if current is None:
        current = _demo_current(vertical)

    offer = _run(vertical, current, profile, explain)
    return {"profile": profile, "offer": offer}


@app.post("/api/compare/{vertical}")
def compare_vertical(
    vertical: str,
    payload: dict = Body(...),
    explain: bool = Query(True, description="B2 why strings; false = bare B1 numbers"),
):
    if vertical not in VERTICALS:
        raise HTTPException(status_code=404, detail="unknown vertical: %s" % vertical)
    return _run(vertical, payload.get("current"), payload.get("needs"), explain)


@app.post("/api/compare-all")
def compare_all(
    payload: dict = Body(...),
    explain: bool = Query(True),
):
    """`current` is the full subscription list (any verticals); `needs` maps
    vertical -> NeedsProfile. Water lines are ignored."""
    current = payload.get("current") or []
    needs_by_vertical = payload.get("needs") or {}

    results = {}
    total_current = 0.0
    total_savings = 0.0
    for vertical in VERTICALS:
        lines = [s for s in current if s.get("vertical") == vertical]
        result = _run(vertical, lines, needs_by_vertical.get(vertical, {}), explain)
        results[vertical] = result
        total_current += result["currentMonthlyEur"] or 0.0
        total_savings += result["monthlySavingsEur"] or 0.0

    return {
        "byVertical": results,
        "totals": {
            "currentMonthlyEur": round(total_current, 2),
            # sum of the savings we could actually quote (energy stays null/0 here)
            "monthlySavingsEur": round(total_savings, 2),
            "annualSavingsEur": round(total_savings * 12, 2),
            "skipped": ["water"],
        },
    }
