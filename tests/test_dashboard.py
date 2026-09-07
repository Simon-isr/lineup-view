"""Fixture-based test for board._team_summary / _projection_key -- the
dashboard's scoring math. Run: python -m tests.test_dashboard (from lineup-view/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board import _projection_key, _team_summary  # noqa: E402

PLAYERS = {
    "1": {"full_name": "Finished Guy", "position": "RB", "team": "KC"},
    "2": {"full_name": "Still Playing", "position": "WR", "team": "BUF"},
    "3": {"full_name": "Not Started", "position": "TE", "team": "DAL"},
}
SCHEDULE = {"KC": {"status": "complete"}, "BUF": {"status": "in_game"}, "DAL": {"status": "pre_game"}}
PROJ = {"1": {"pts_half_ppr": 8.0}, "2": {"pts_half_ppr": 12.0}, "3": {"pts_half_ppr": 6.0}}


def test_projection_key():
    assert _projection_key({"scoring_settings": {"rec": 1.0}}) == "pts_ppr"
    assert _projection_key({"scoring_settings": {"rec": 0.5}}) == "pts_half_ppr"
    assert _projection_key({"scoring_settings": {"rec": 0}}) == "pts_std"
    assert _projection_key({}) == "pts_std"


def test_team_summary_blends_actual_and_projection():
    row = {
        "points": 25.5,
        "starters": ["1", "2", "3"],
        "players_points": {"1": 14.0, "2": 9.0, "3": 0.0},
    }
    summary = _team_summary(row, PLAYERS, SCHEDULE, PROJ, "pts_half_ppr")
    assert summary["score"] == 25.5
    # finished game -> actual (14.0); in-game -> max(actual 9.0, proj 12.0) = 12.0;
    # not started -> proj 6.0
    assert summary["projected"] == 14.0 + 12.0 + 6.0
    assert summary["yet_to_play"] == ["Not Started"]
    assert summary["yet_to_play_count"] == 1


def test_team_summary_none_row():
    assert _team_summary(None, PLAYERS, SCHEDULE, PROJ, "pts_half_ppr") is None


if __name__ == "__main__":
    test_projection_key()
    test_team_summary_blends_actual_and_projection()
    test_team_summary_none_row()
    print("ok")
