"""Lineup View -- my players vs. my opponents' players, across every Sleeper
league I'm in, plus a "playing now" filter for live game weeks.

    python -m uvicorn server:app --port 8779 --reload
    open http://localhost:8779/?user=SimonIsr

One endpoint (/api/appearances) returns a flat list of {league, side,
player, is_starter, is_live, ...} rows; the frontend slices it per-league and
for the "playing now" toggle. See board.py's docstring for why one shape.
"""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import board

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Optional GA4 property to send analytics to (page views, time on site, and
# the click events static/analytics.js + app.js/dashboard.js fire). Unset in
# local dev -- _ga_snippet() returns "" and the pages load with no analytics
# script at all, so there's nothing to configure to keep working locally.
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID")

app = FastAPI(title="Lineup View")


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


@app.get("/all-players")
def all_players_shortcut():
    """A memorable, typeable URL for a view that's otherwise two checkboxes
    deep -- redirects to the same "All players" + "Group by game time" state
    app.js already knows how to apply from ?all=1&group=1 (see its
    deep-link comment)."""
    return RedirectResponse(url="/?all=1&group=1")


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
