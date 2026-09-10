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

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
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
APP_PASSWORD = os.environ.get("APP_PASSWORD")

# Optional GA4 property to send analytics to (page views, time on site, and
# the click events static/analytics.js + app.js/dashboard.js fire). Unset in
# local dev -- _ga_snippet() returns "" and the pages load with no analytics
# script at all, so there's nothing to configure to keep working locally.
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not APP_PASSWORD:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                username, _, password = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            except Exception:
                username, password = "", ""
            if secrets.compare_digest(password, APP_PASSWORD):
                # The password is what's actually checked -- username is a
                # free-text label whoever's logging in chooses. Stash it so
                # /api/whoami (and therefore GA, via analytics.js) can show
                # who's using the app instead of an anonymous session.
                request.state.app_user = username or None
                return await call_next(request)
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Lineup View"'})


app = FastAPI(title="Lineup View")
app.add_middleware(BasicAuthMiddleware)


def _ga_snippet() -> str:
    if not GA_MEASUREMENT_ID:
        return ""
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>\n'
        "<script>\n"
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){ dataLayer.push(arguments); }\n"
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{GA_MEASUREMENT_ID}');\n"
        "</script>"
    )


def _render_page(path: Path) -> HTMLResponse:
    html = path.read_text(encoding="utf-8").replace("<!--GA_SNIPPET-->", _ga_snippet())
    return HTMLResponse(html)


@app.get("/")
def index():
    return _render_page(STATIC_DIR / "index.html")


@app.get("/dashboard")
def dashboard_page():
    return _render_page(STATIC_DIR / "dashboard.html")


@app.get("/api/whoami")
def whoami(request: Request):
    """The Basic Auth username for this request, if any -- read by
    analytics.js so GA can label a visit with a real name instead of an
    anonymous session. Not an authentication check (see BasicAuthMiddleware);
    just exposing what it already parsed."""
    return {"app_user": getattr(request.state, "app_user", None)}


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
