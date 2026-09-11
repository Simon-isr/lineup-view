"""Core logic: resolve a Sleeper id, discover every league, and build one flat
list of "appearances" -- one row per (league, side, player) -- that both the
per-league board view and the "playing now" view are just filters over.

Deliberately ONE data shape for both views (see notes.md): the board view
groups appearances by league and side; the live view filters the same list to
is_starter and is_live. No separate code path to keep in sync.
"""
import json
import sys
from pathlib import Path
from typing import Optional

import espn
import lineup
import sleeper

NOT_LIVE_STATUSES = {"pre_game", "complete", "final", "postponed", "canceled", "cancelled"}
COMPLETE_STATUSES = {"complete", "final"}

MANUAL_LEAGUES_PATH = Path(__file__).resolve().parent / "manual_leagues.json"
BENCH_SLOTS = {"BN", "IR"}

# manual_leagues.json is Simon's own hand-maintained ESPN roster -- anyone
# else using the app (it's a shared, unauthenticated-by-username tool once
# hosted) should never see it show up in their leagues. Gate it to just his
# Sleeper username rather than dropping it in for every viewer.
MANUAL_LEAGUES_OWNER = "simonisr"


def _load_manual_leagues() -> list:
    """Leagues tracked by hand instead of through a live API -- built for a
    platform (ESPN) not worth wiring up real integration for one league:
    paste an updated roster/projections into manual_leagues.json instead
    (ESPN's fantasy API needs cookie auth per league, unlike Sleeper's fully
    public one -- see YAHOO_INTEGRATION.md for the same tradeoff on Yahoo).
    No live scoring: `points`/`projected` are exactly whatever's in the file,
    refreshed only when it's edited. Game status/kickoff still come from the
    real NFL schedule (schedule_by_team/kickoff_by_team, built once below and
    shared with every Sleeper league) since those don't depend on which
    fantasy platform the league runs on. See README's 'Manual leagues'
    section for the file format and how to refresh it."""
    if not MANUAL_LEAGUES_PATH.exists():
        return []
    return json.loads(MANUAL_LEAGUES_PATH.read_text(encoding="utf-8")).get("leagues", [])


def is_live(status: Optional[str]) -> bool:
    """A game counts as live if its status isn't a known not-live value.
    Deliberately a denylist, not an allowlist of e.g. {'in_game'} -- Sleeper's
    schedule endpoint is undocumented, and an allowlist silently hides real
    live games the first time it uses a status string we haven't seen (halftime,
    delayed, etc). See tests/test_live_filter.py for the fixture that pins this."""
    if not status:
        return False
    return status not in NOT_LIVE_STATUSES


def _player_info(player_id: str, players: dict) -> dict:
    p = players.get(player_id)
    if p:
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        return {
            "name": name or player_id,
            "pos": p.get("position") or "?",
            "team": p.get("team"),
            # Sleeper's own multi-eligibility list (e.g. a player who also
            # qualifies at another position) -- lineup.py's slot-eligibility
            # check needs this, not just `pos`, or a multi-eligible player
            # gets wrongly excluded from a flex slot he can legally fill.
            "fantasy_positions": p.get("fantasy_positions") or [],
            "injury_status": p.get("injury_status"),
        }
    # Team defenses are keyed by team code directly in some dumps; others aren't
    # present at all. Synthesize rather than show a bare code.
    if player_id.isalpha() and player_id.isupper() and len(player_id) <= 3:
        return {"name": f"{player_id} D/ST", "pos": "DEF", "team": player_id,
                "fantasy_positions": ["DEF"], "injury_status": None}
    return {"name": player_id, "pos": "?", "team": None, "fantasy_positions": [], "injury_status": None}


def _team_game_status(team: Optional[str], schedule_by_team: dict) -> Optional[str]:
    if not team:
        return None
    game = schedule_by_team.get(team)
    return game["status"] if game else None


def _projection_key(league_settings: dict) -> str:
    """Sleeper's weekly projections ship pts_ppr/pts_half_ppr/pts_std pre-computed
    -- pick the variant matching this league's `rec` scoring setting rather than
    doing scoring math ourselves. Approximate for a league with other custom
    scoring (TE premium, bonuses, ...): those three variants are the closest
    match Sleeper offers, not an exact replica of a heavily customized league."""
    rec = ((league_settings or {}).get("scoring_settings") or {}).get("rec", 0) or 0
    if rec >= 0.99:
        return "pts_ppr"
    if rec >= 0.49:
        return "pts_half_ppr"
    return "pts_std"


def _blend_points(actual: float, status: Optional[str], proj_val: float) -> float:
    """One player's projected-final contribution: actual once his game is done,
    else whichever is larger of (points already accrued live) or (the
    pre-kickoff weekly projection) -- a simple heuristic, not a live in-game
    re-projection: it won't raise a projection mid-game as a player outperforms
    it beyond what's already on the board. Shared by _team_summary (a roster's
    total) and build_appearances (per-player, for the same number shown next to
    each row) so the two can never drift apart."""
    if status in COMPLETE_STATUSES:
        return actual
    return max(actual, proj_val or 0.0)


def _team_summary(row: Optional[dict], players: dict, schedule_by_team: dict,
                   proj_by_id: dict, proj_key: str) -> Optional[dict]:
    """Score, projected final score, and who hasn't played yet -- for one
    roster's starters in one week. Good enough for "roughly where this team
    lands", not a precise in-game win-probability model -- see _blend_points."""
    if row is None:
        return None
    starters = [s for s in (row.get("starters") or []) if s and s != "0"]
    points_by_id = row.get("players_points") or {}
    projected = 0.0
    yet_to_play = []
    for pid in starters:
        info = _player_info(pid, players)
        status = _team_game_status(info["team"], schedule_by_team)
        actual = points_by_id.get(pid, 0.0)
        proj_val = (proj_by_id.get(pid) or {}).get(proj_key) or 0.0
        projected += _blend_points(actual, status, proj_val)
        if not status or status == "pre_game":
            yet_to_play.append(info["name"])
    return {
        "score": row.get("points", 0.0),
        "projected": round(projected, 2),
        "yet_to_play": yet_to_play,
        "yet_to_play_count": len(yet_to_play),
    }


def resolve_user(username_or_id: str) -> dict:
    u = sleeper.get_user(username_or_id)
    if not u:
        raise ValueError(f"no Sleeper user found for {username_or_id!r}")
    return {"user_id": u["user_id"], "username": u.get("username") or u.get("display_name")}


def build_appearances(username_or_id: str, week: Optional[int] = None, force: bool = False) -> dict:
    """force=True bypasses sleeper.py's short-TTL caches (rosters, matchups,
    schedule, state) instead of waiting them out -- for the /start-sit
    Refresh button, where "pull live data" should mean live, not
    "whatever's still under 30s old". Left False for a normal page load: the
    caches are already short enough that nothing here is meaningfully stale,
    and forcing on every load would turn a free page view into a guaranteed
    round trip to Sleeper for no benefit."""
    user = resolve_user(username_or_id)
    user_id = user["user_id"]

    state = sleeper.get_state_nfl(force=force)
    season = state["season"]
    season_type = state.get("season_type", "regular")
    current_week = state["week"]
    week = week or current_week or 1
    is_past_week = week < current_week

    schedule = sleeper.get_schedule(season, season_type, force=force)
    schedule_by_team = {}
    for g in schedule:
        if g.get("week") != week:
            continue
        schedule_by_team[g["home"]] = g
        schedule_by_team[g["away"]] = g

    # Kickoff time, for the frontend's "group by game time" view -- a second,
    # ESPN-sourced schedule (see espn.py's docstring for why) rather than
    # something Sleeper's own schedule carries. Best-effort: a player just
    # gets no kickoff (frontend falls back to one ungrouped bucket) rather
    # than the whole page breaking over a display grouping.
    try:
        kickoff_by_team = espn.get_kickoff_by_team(season, week, season_type)
    except Exception as e:
        print(f"kickoff lookup failed, grouping by game time will be unavailable: {e}", file=sys.stderr)
        kickoff_by_team = {}

    players = sleeper.get_players()

    # Format-agnostic raw stats -- fetched once, keyed by player_id, reused
    # across all leagues; each league picks its own scoring variant from it.
    proj_by_id = {p["player_id"]: (p.get("stats") or {})
                  for p in sleeper.get_week_projections(season, week, season_type)
                  if p.get("player_id")}

    leagues_raw = sleeper.get_user_leagues(user_id, season)
    leagues_out = []
    appearances = []

    for lg in leagues_raw:
        league_id = lg["league_id"]
        league_name = lg["name"]
        status = lg.get("status")  # pre_draft | drafting | in_season | complete
        entry = {"league_id": league_id, "name": league_name, "status": status}
        leagues_out.append(entry)

        if status not in ("in_season", "complete"):
            entry["note"] = "not rosterable yet (pre-draft/drafting)"
            continue

        rosters = sleeper.get_rosters(league_id, force=force)
        users = sleeper.get_league_users(league_id)
        owner_name = {
            u["user_id"]: (u.get("metadata") or {}).get("team_name") or u.get("display_name") or u["user_id"]
            for u in users
        }

        my_roster = next(
            (r for r in rosters
             if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or [])),
            None,
        )
        if my_roster is None:
            entry["note"] = "not a member of this roster (spectating?)"
            continue

        try:
            matchups = sleeper.get_matchups(league_id, week, is_past_week, force=force)
        except Exception as e:
            entry["note"] = f"matchups unavailable: {e}"
            continue

        my_row = next((m for m in matchups if m["roster_id"] == my_roster["roster_id"]), None)
        if my_row is None or my_row.get("matchup_id") is None:
            entry["note"] = "bye week or matchups not yet posted"
            continue

        opp_row = next(
            (m for m in matchups
             if m["matchup_id"] == my_row["matchup_id"] and m["roster_id"] != my_row["roster_id"]),
            None,
        )
        opp_roster = next((r for r in rosters if r.get("roster_id") == (opp_row or {}).get("roster_id")), None)
        opp_owner = owner_name.get((opp_roster or {}).get("owner_id"), "Opponent") if opp_row else None
        my_owner = owner_name.get(my_roster.get("owner_id"), "Me")

        league_settings = sleeper.get_league(league_id)
        proj_key = _projection_key(league_settings)

        def _rows(row, side, this_owner, other_owner):
            out = []
            if row is None:
                return out
            starters = set(s for s in (row.get("starters") or []) if s and s != "0")
            points_by_id = row.get("players_points") or {}
            for pid in row.get("players") or []:
                info = _player_info(pid, players)
                game_status = _team_game_status(info["team"], schedule_by_team)
                actual = points_by_id.get(pid, 0.0)
                proj_val = (proj_by_id.get(pid) or {}).get(proj_key) or 0.0
                appearance = {
                    "league_id": league_id,
                    "league_name": league_name,
                    "side": side,
                    "owner_name": this_owner,
                    "opponent_name": other_owner,
                    "player_id": pid,
                    "name": info["name"],
                    "pos": info["pos"],
                    "team": info["team"],
                    "fantasy_positions": info["fantasy_positions"],
                    "injury_status": info["injury_status"],
                    "is_starter": pid in starters,
                    "points": actual,
                    "projected": round(_blend_points(actual, game_status, proj_val), 2),
                    "game_status": game_status,
                    "is_live": is_live(game_status),
                    "kickoff": kickoff_by_team.get(info["team"]),
                }
                appearances.append(appearance)
                out.append(appearance)
            return out

        mine_rows = _rows(my_row, "mine", my_owner, opp_owner)
        _rows(opp_row, "theirs", opp_owner, my_owner)

        entry["my_owner"] = my_owner
        entry["opp_owner"] = opp_owner
        entry["my"] = _team_summary(my_row, players, schedule_by_team, proj_by_id, proj_key)
        entry["opp"] = _team_summary(opp_row, players, schedule_by_team, proj_by_id, proj_key)

        # Start/sit recommendation -- see lineup.py. Needs the league's slot
        # structure (roster_positions) and which appearance currently sits in
        # each non-bench slot; the latter relies on Sleeper's `starters` array
        # being ordered to match roster_positions minus bench slots
        # (empirically verified against every league in .cache/, see
        # tests/test_lineup.py).
        roster_positions = league_settings.get("roster_positions") or []
        starting_slots = [s for s in roster_positions if s not in lineup.BENCH_LIKE]
        if roster_positions and mine_rows and my_row is not None:
            by_id = {a["player_id"]: a for a in mine_rows}
            raw_starters = my_row.get("starters") or []
            current_by_slot = [
                by_id.get(raw_starters[i]) if i < len(raw_starters) and raw_starters[i] not in (None, "0") else None
                for i in range(len(starting_slots))
            ]
            entry["lineup_recommendation"] = lineup.recommend_lineup(mine_rows, roster_positions, current_by_slot)

    manual_leagues = _load_manual_leagues() if (user["username"] or "").lower() == MANUAL_LEAGUES_OWNER else []
    for lg in manual_leagues:
        league_id = lg["league_id"]
        league_name = lg["name"]
        my_owner = user["username"]
        opp_owner = lg.get("opponent_name")  # None until the opponent's roster is worth tracking too
        leagues_out.append({"league_id": league_id, "name": league_name, "status": "in_season",
                             "my_owner": my_owner, "opp_owner": opp_owner})

        starters_points = starters_proj = 0.0
        manual_rows = []
        for p in lg.get("roster", []):
            pid = p.get("sleeper_id") or f"manual:{league_id}:{p.get('name')}"
            # A known sleeper_id gets name/pos/team the same way every other
            # league does (_player_info), so this player merges into the
            # right cross-league tag row in the "All players" view instead of
            # showing up as an unrelated duplicate.
            info = _player_info(pid, players) if p.get("sleeper_id") else {
                "name": p.get("name", pid), "pos": p.get("pos", "?"), "team": p.get("team"),
                "fantasy_positions": [p.get("pos", "?")], "injury_status": None}
            game_status = _team_game_status(info["team"], schedule_by_team)
            is_starter = p.get("slot") not in BENCH_SLOTS
            points = p.get("points") or 0.0
            projected = p.get("projected")
            projected = points if projected is None else projected
            appearance = {
                "league_id": league_id,
                "league_name": league_name,
                "side": "mine",
                "owner_name": my_owner,
                "opponent_name": opp_owner,
                "player_id": pid,
                "name": info["name"],
                "pos": info["pos"],
                "team": info["team"],
                "fantasy_positions": info["fantasy_positions"],
                "injury_status": info["injury_status"],
                "is_starter": is_starter,
                "points": points,
                "projected": round(projected, 2),
                "game_status": game_status,
                "is_live": is_live(game_status),
                "kickoff": kickoff_by_team.get(info["team"]) if info["team"] else None,
            }
            appearances.append(appearance)
            manual_rows.append(appearance)
            if is_starter:
                starters_points += points
                starters_proj += projected

        entry = next(e for e in leagues_out if e["league_id"] == league_id)
        entry["my"] = {"score": round(starters_points, 2), "projected": round(starters_proj, 2),
                        "yet_to_play": [], "yet_to_play_count": 0}
        entry["opp"] = None  # no opponent roster tracked -- see opp_owner above

        # Start/sit recommendation -- manual_leagues.json's per-player "slot"
        # field IS this league's roster_positions/current-slot info (one
        # entry per rostered player, in slot order), so no separate schema
        # is needed the way a real Sleeper league needs `starters` zipped
        # against roster_positions. See lineup.py.
        roster_positions = [p.get("slot") for p in lg.get("roster", [])]
        current_by_slot = [row for row, p in zip(manual_rows, lg.get("roster", []))
                            if p.get("slot") not in lineup.BENCH_LIKE]
        if roster_positions:
            entry["lineup_recommendation"] = lineup.recommend_lineup(manual_rows, roster_positions, current_by_slot)

    return {
        "user": user,
        "season": season,
        "week": week,
        "current_week": current_week,
        "leagues": leagues_out,
        "appearances": appearances,
    }
