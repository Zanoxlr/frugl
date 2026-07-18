"""Dev runner: ONE Frugl PWA + backend from ONE origin.

    python -m uvicorn dev_serve:app --port 8000 --app-dir .

  /            -> the whole PWA: `landing/index.html` (pitch + quiz + objection +
                  the app: dashboard / chat / needs-card, opened in-place via App.open()).
  /api/*       -> Zan's API (registered on `app` before the mount, so it wins).

The former separate `frontend/` app is now merged INTO the landing (one file, one
manifest, one service worker) — nothing else to serve. Absolute path so it runs from
any cwd. Does NOT modify backend/main.py.
"""
import os

from fastapi.staticfiles import StaticFiles

from backend.main import app  # Zan's API, routes already registered

_HERE = os.path.dirname(os.path.abspath(__file__))

# The one PWA at root; /api/* routes (registered earlier) still win.
app.mount("/", StaticFiles(directory=os.path.join(_HERE, "landing"), html=True), name="pwa")
