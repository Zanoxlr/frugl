"""Dev runner: ONE origin serves the whole Frugl PWA + backend, so it installs as a
single app and the landing -> app flow is continuous.

    python -m uvicorn dev_serve:app --port 8000 --app-dir .

  /            -> landing (marketing + quiz + objection flow)
  /app         -> the app (dashboard / chat / needs-card, on the live backend)
  /api/*       -> Zan's API (registered on `app` before these mounts, so it wins)

Absolute paths so it runs from any cwd. Does NOT modify backend/main.py.
"""
import os

from fastapi.staticfiles import StaticFiles

from backend.main import app  # Zan's API, routes already registered

_HERE = os.path.dirname(os.path.abspath(__file__))

# /app first so it wins over the root catch-all; landing mounted at root last.
app.mount("/app", StaticFiles(directory=os.path.join(_HERE, "frontend"), html=True), name="app")
app.mount("/", StaticFiles(directory=os.path.join(_HERE, "landing"), html=True), name="landing")
