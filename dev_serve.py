"""Dev runner: serve the FastAPI backend + the static frontend from ONE origin,
so the frontend's same-origin `fetch("/api/...")` works with no CORS.

    python -m uvicorn dev_serve:app --port 8000 --app-dir .

API stays at /api/*, the app is served at /. Does NOT modify backend/main.py.
Uses an absolute path for the frontend dir so it works regardless of the cwd.
"""
import os

from fastapi.staticfiles import StaticFiles

from backend.main import app  # Zan's API, routes already registered

_HERE = os.path.dirname(os.path.abspath(__file__))
# Mounted last so /api/* routes (registered earlier) win; everything else -> frontend.
app.mount("/", StaticFiles(directory=os.path.join(_HERE, "frontend"), html=True), name="frontend")
