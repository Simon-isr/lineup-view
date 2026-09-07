"""Minimal vendored Sleeper client for lineup-view.

Vendored rather than imported from `league-commentator/lc/sleeper.py` or
`core/`/`2026 Auction/app/` on purpose, matching this repo's own convention
(see league-commentator/VENDORED.md) — this project only needs ~8 read-only
endpoints and no DB, so a cross-project import would buy coupling for nothing.

Cache policy (same split as lc/sleeper.py, reproduced because it's the right
call, not because the code is shared):
- IMMUTABLE: a past week's matchups never change. Cached forever.
- CURRENT-STATE: rosters, this week's matchups, schedule/game-status, the
  player dump. Short TTL, and on fetch failure we RAISE rather than serve a
  stale copy — a live "who's playing now" view showing a stale game status
  is actively misleading, worse than an error.
"""
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

BASE_V1 = "https://api.sleeper.app/v1"
BASE = "https://api.sleeper.app"

_session = requests.Session()


def _get(url: str, params=None):
    r = _session.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _cache_path(name: str) -> Path:
    return CACHE_DIR / name


def _immutable(name: str, url: str, params=None):
    path = _cache_path(name)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = _get(url, params)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _current(name: str, url: str, params=None, max_age_seconds: float = 3600):
    path = _cache_path(name)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < max_age_seconds:
            return json.loads(path.read_text(encoding="utf-8"))
    data = _get(url, params)  # raises on failure -- no stale fallback, by design
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


# ---- user / league discovery ----

def get_user(username_or_id: str) -> dict:
    """Resolves a Sleeper username OR a numeric user_id to the user object.
    Works for both because Sleeper's /user/{x} endpoint accepts either."""
    return _current(f"user_{username_or_id}.json", f"{BASE_V1}/user/{username_or_id}",
                     max_age_seconds=86400)


def get_user_leagues(user_id: str, season: str) -> list:
    """Every league this user is in for the season -- no static per-league config,
    by design (see PROJECT context: the whole point is discovering all of them,
    not hardcoding a known set that will silently miss a new league)."""
    return _current(f"leagues_{user_id}_{season}.json",
                     f"{BASE_V1}/user/{user_id}/leagues/nfl/{season}", max_age_seconds=300)


def get_state_nfl() -> dict:
    return _current("state_nfl.json", f"{BASE_V1}/state/nfl", max_age_seconds=1800)


# ---- per-league ----

def get_league(league_id: str) -> dict:
    """League settings incl. scoring_settings -- used to pick which projection
    variant (pts_ppr / pts_half_ppr / pts_std) matches this league's format."""
    return _current(f"league_{league_id}.json", f"{BASE_V1}/league/{league_id}",
                     max_age_seconds=21600)


def get_league_users(league_id: str) -> list:
    return _current(f"users_{league_id}.json", f"{BASE_V1}/league/{league_id}/users",
                     max_age_seconds=1800)


def get_rosters(league_id: str) -> list:
    return _current(f"rosters_{league_id}.json", f"{BASE_V1}/league/{league_id}/rosters",
                     max_age_seconds=300)


def get_matchups(league_id: str, week: int, is_past: bool) -> list:
    name = f"matchups_{league_id}_wk{week:02d}.json"
    url = f"{BASE_V1}/league/{league_id}/matchups/{week}"
    if is_past:
        return _immutable(name, url)
    return _current(name, url, max_age_seconds=30)


# ---- players + live schedule ----

def get_players() -> dict:
    """Full NFL player dump (~5-15MB), keyed by player_id. Refreshed daily --
    Sleeper asks for at most one call/day to this endpoint."""
    return _current("players_nfl.json", f"{BASE_V1}/players/nfl", max_age_seconds=86400)


def get_week_projections(season: str, week: int, season_type: str = "regular") -> list:
    """Weekly per-player projections. Each entry's `stats` dict carries several
    pre-computed scoring variants (pts_ppr / pts_half_ppr / pts_std, ...) --
    same convention as the season-long ADP endpoint -- so no scoring math is
    needed, just picking the variant matching a league's `rec` setting (see
    board.py's _projection_key). Short TTL: projections drift all week."""
    params = [("season_type", season_type)] + [("position[]", p) for p in
               ("QB", "RB", "WR", "TE", "K", "DEF")]
    return _current(f"projections_{season_type}_{season}_wk{week:02d}.json",
                     f"{BASE}/projections/nfl/{season}/{week}", params=params, max_age_seconds=1800)


def get_schedule(season: str, season_type: str = "regular") -> list:
    """Undocumented per-game schedule + live status, in Sleeper's own team codes
    (so it lines up with the player dump's `team` field with no crosswalk needed --
    unlike an ESPN-sourced schedule, which would need a hand-maintained code map).
    Entries carry {status, date, home, away, week, game_id}; `status` seen so far:
    'pre_game' pre-kickoff. Treated as a live/not-live boolean in board.py, not by
    an exhaustive enum -- see board.py's is_live() for why.

    `season_type` MUST come from /state/nfl, not a literal 'regular' -- during
    the fantasy playoffs (Jan) state reports 'post', and the regular-season
    schedule path has no entries for those weeks, which would silently make
    every game_status None (i.e. "not live") for the entire playoffs."""
    return _current(f"schedule_{season_type}_{season}.json",
                     f"{BASE}/schedule/nfl/{season_type}/{season}", max_age_seconds=30)
