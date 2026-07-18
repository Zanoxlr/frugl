"""Dev runner: serve the FastAPI backend + the static frontend from ONE origin,
so the frontend's same-origin `fetch("/api/...")` works with no CORS.

    python -m uvicorn dev_serve:app --port 8000 --app-dir .

API stays at /api/*, the app is served at /. Does NOT modify backend/main.py.
"""
from fastapi.staticfiles import StaticFiles

from backend.main import app  # Zan's API, routes already registered

# Mounted last so /api/* routes (registered earlier) win; everything else -> frontend.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
