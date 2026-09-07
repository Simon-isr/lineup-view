"""Lineup View -- my players vs. my opponents' players, across every Sleeper
league I'm in, plus a "playing now" filter for live game weeks.

    python -m uvicorn server:app --port 8779 --reload
    open http://localhost:8779/?user=SimonIsr

One endpoint (/api/appearances) returns a flat list of {league, side,
player, is_starter, is_live, ...} rows; the frontend slices it per-league and
for the "playing now" toggle. See board.py's docstring for why one shape.
"""
import base64
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import board

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Gate the whole app (static files, HTML, API -- everything) behind one
# shared password once this is hosted somewhere reachable from any WiFi,
# via plain HTTP Basic Auth: the browser's own native username/password
# prompt, so there's no login page to build and it works identically on
# desktop and mobile. Only active when APP_PASSWORD is set -- local dev
# stays exactly as open as before, no env var to remember day to day.
# Username is ignored; only the password is checked.
APP_PASSWORD = os.environ.get("APP_PASSWORD")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not APP_PASSWORD:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, password = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            except Exception:
                password = ""
            if secrets.compare_digest(password, APP_PASSWORD):
                return await call_next(request)
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Lineup View"'})


app = FastAPI(title="Lineup View")
app.add_middleware(BasicAuthMiddleware)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/api/appearances")
def appearances(user: str = Query(..., description="Sleeper username or user_id"),
                 week: int = Query(None, ge=1, le=18)):
    try:
        return board.build_appearances(user, week)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sleeper fetch failed: {e}")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
