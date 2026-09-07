"""Kickoff-time lookup from ESPN's public scoreboard endpoint.

Sleeper's own schedule (sleeper.get_schedule) carries a game's *date* but no
time-of-day -- fine for board.is_live()'s status check, useless for "how far
apart are these two kickoffs", which the All Players "group by game time"
view needs. ESPN's undocumented-but-public scoreboard endpoint carries a
full ISO kickoff timestamp per game and needs no auth key.

Deliberately a *second* schedule source rather than folding into
sleeper.get_schedule -- that one's `status` field (live/final/etc, refreshed
every 30s) is what board.is_live() depends on and is unrelated to what this
module does (a kickoff time, fixed once the week's slate is set, flex
scheduling aside). Mixing them would mean a flaky ESPN call could take down
the live-status view it has nothing to do with.

Team codes: verified against the full week 1 2026 slate (all 32 teams) --
ESPN's scoreboard uses the same abbreviations as Sleeper's player dump/
schedule for every team except Washington (`WSH` here vs `WAS` there).
ESPN_TO_SLEEPER below is that one-entry crosswalk. If a future ESPN rename
introduces another mismatch, that team's players just fall into board.py's
"unknown kickoff" bucket rather than erroring -- acceptable for a display
grouping, not worth an assert that would turn a cosmetic mismatch into a
broken page.

Failure policy: unlike sleeper.py's "raise rather than serve stale" (a stale
*live status* is actively misleading), a failed or slow ESPN call here should
never break /api/appearances -- a missing kickoff time just drops every
player into one ungrouped bucket in the frontend. board.py is expected to
catch and swallow exceptions from get_kickoff_by_team, not this module.
"""
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# Sleeper's /state/nfl reports season_type as pre|regular|post (see
# sleeper.get_schedule's docstring for why that MUST drive this, not a
# hardcoded 2 -- during the fantasy playoffs state reports 'post', and the
# wrong seasontype here would silently return zero events for the week).
SEASON_TYPE = {"pre": 1, "regular": 2, "post": 3}

ESPN_TO_SLEEPER = {"WSH": "WAS"}

_session = requests.Session()


def get_kickoff_by_team(season: str, week: int, season_type: str = "regular") -> dict:
    """{team_code: kickoff_iso_utc} for every team with a game this week, keyed
    in Sleeper's own team codes. Cached for an hour -- kickoff times are set
    for the week but flex scheduling can still move a late-season game on
    ~12 days' notice, so this isn't cached for the rest of the week outright."""
    params = {"week": week, "seasontype": SEASON_TYPE.get(season_type, 2), "year": season}
    name = f"espn_kickoffs_{season_type}_{season}_wk{week:02d}.json"
    path = CACHE_DIR / name
    if path.exists() and (time.time() - path.stat().st_mtime) < 3600:
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        r = _session.get(BASE, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        path.write_text(json.dumps(data), encoding="utf-8")

    out = {}
    for e in data.get("events") or []:
        kickoff = e.get("date")
        comp = (e.get("competitions") or [{}])[0]
        for c in comp.get("competitors") or []:
            code = (c.get("team") or {}).get("abbreviation")
            if not code:
                continue
            out[ESPN_TO_SLEEPER.get(code, code)] = kickoff
    return out
