"""Fixture-based test for lineup.recommend_lineup() -- pins Simon's own
stated heuristic (2 RB slots + 1 FLEX, 3 RBs worth starting -> the RB
playing last goes in FLEX) plus the guardrails around it: the optionality
pass never changes who starts, and a locked slot is never touched.
Run: python -m tests.test_lineup (from lineup-view/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lineup import recommend_lineup  # noqa: E402

ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF", "K", "BN", "BN", "BN"]


def _player(pid, name, pos, projected, kickoff, game_status="pre_game", injury_status=None):
    return {
        "player_id": pid, "name": name, "pos": pos, "team": pid,
        "fantasy_positions": [pos], "injury_status": injury_status,
        "points": 0.0, "projected": projected, "game_status": game_status, "kickoff": kickoff,
    }


def test_latest_kickoff_rb_goes_to_flex():
    roster = [
        _player("qb1", "QB One", "QB", 20.0, "2026-09-14T17:00:00Z"),
        _player("rb1", "Early RB", "RB", 15.0, "2026-09-14T13:00:00Z"),
        _player("rb2", "Mid RB", "RB", 14.0, "2026-09-14T17:00:00Z"),
        _player("rb3", "Late RB", "RB", 13.0, "2026-09-15T00:15:00Z"),  # Monday night
        _player("wr1", "WR One", "WR", 12.0, "2026-09-14T13:00:00Z"),
        _player("wr2", "WR Two", "WR", 11.0, "2026-09-14T13:00:00Z"),
        _player("te1", "TE One", "TE", 8.0, "2026-09-14T13:00:00Z"),
        _player("def1", "DEF One", "DEF", 7.0, "2026-09-14T13:00:00Z"),
        _player("k1", "K One", "K", 6.0, "2026-09-14T13:00:00Z"),
        _player("wr3", "Bench WR", "WR", 4.0, "2026-09-14T13:00:00Z"),
    ]
    # Nothing currently started -- an empty lineup, so every recommended
    # starter shows up as a "Start" note rather than a slot move.
    current_by_slot = [None] * 8

    rec = recommend_lineup(roster, ROSTER_POSITIONS, current_by_slot)
    by_slot = {s["slot"]: s for s in rec["slots"]}

    # All three RBs make the starting lineup (the two dedicated RB slots
    # plus FLEX) -- the player-set decision, unaffected by kickoff order.
    assert by_slot["RB"]["recommended"]["player_id"] != by_slot["FLEX"]["recommended"]["player_id"]
    started_rb_ids = {
        by_slot["FLEX"]["recommended"]["player_id"],
    }
    rb_slots = [s for s in rec["slots"] if s["slot"] == "RB"]
    started_rb_ids |= {s["recommended"]["player_id"] for s in rb_slots}
    assert started_rb_ids == {"rb1", "rb2", "rb3"}

    # The literal ask: whichever RB plays LAST sits in FLEX, not a dedicated
    # RB slot, regardless of his (slightly lower) projection.
    assert by_slot["FLEX"]["recommended"]["player_id"] == "rb3"
    assert all(s["recommended"]["player_id"] != "rb3" for s in rb_slots)


def test_optionality_pass_does_not_change_who_starts():
    roster = [
        _player("qb1", "QB One", "QB", 20.0, "2026-09-14T17:00:00Z"),
        _player("rb1", "Early RB", "RB", 15.0, "2026-09-14T13:00:00Z"),
        _player("rb2", "Mid RB", "RB", 14.0, "2026-09-14T17:00:00Z"),
        _player("rb3", "Late RB", "RB", 13.0, "2026-09-15T00:15:00Z"),
        _player("wr1", "WR One", "WR", 12.0, "2026-09-14T13:00:00Z"),
        _player("wr2", "WR Two", "WR", 11.0, "2026-09-14T13:00:00Z"),
        _player("te1", "TE One", "TE", 8.0, "2026-09-14T13:00:00Z"),
        _player("def1", "DEF One", "DEF", 7.0, "2026-09-14T13:00:00Z"),
        _player("k1", "K One", "K", 6.0, "2026-09-14T13:00:00Z"),
    ]
    current_by_slot = [None] * 8
    rec = recommend_lineup(roster, ROSTER_POSITIONS, current_by_slot)
    started = {s["recommended"]["player_id"] for s in rec["slots"] if s["recommended"]}
    assert started == {"qb1", "rb1", "rb2", "rb3", "wr1", "wr2", "te1", "def1", "k1"}


def test_locked_slot_is_never_touched():
    roster = [
        _player("qb1", "QB One", "QB", 20.0, "2026-09-14T17:00:00Z"),
        # Already in the RB slot and live -- Sleeper wouldn't let this move
        # even though a bench RB projects higher.
        _player("rb1", "Locked RB", "RB", 5.0, "2026-09-14T13:00:00Z", game_status="in_game"),
        _player("rb2", "Bench RB", "RB", 25.0, "2026-09-14T17:00:00Z"),
        _player("wr1", "WR One", "WR", 12.0, "2026-09-14T13:00:00Z"),
        _player("wr2", "WR Two", "WR", 11.0, "2026-09-14T13:00:00Z"),
        _player("te1", "TE One", "TE", 8.0, "2026-09-14T13:00:00Z"),
        _player("def1", "DEF One", "DEF", 7.0, "2026-09-14T13:00:00Z"),
        _player("k1", "K One", "K", 6.0, "2026-09-14T13:00:00Z"),
    ]
    current_by_slot = [None, roster[1], None, None, None, None, None, None]  # rb1 seated in the 1st RB slot
    rec = recommend_lineup(roster, ROSTER_POSITIONS, current_by_slot)
    rb_slots = [s for s in rec["slots"] if s["slot"] == "RB"]
    locked = next(s for s in rb_slots if s["locked"])
    assert locked["current"]["player_id"] == "rb1"
    assert locked["recommended"]["player_id"] == "rb1"  # unchanged despite rb2's higher projection
    assert not any("Locked RB" in n for n in rec["notes"])  # no note generated for a slot that can't move


if __name__ == "__main__":
    test_latest_kickoff_rb_goes_to_flex()
    test_optionality_pass_does_not_change_who_starts()
    test_locked_slot_is_never_touched()
    print("ok")
