"""Fixture-based test for board.is_live() -- the one piece of this app that
can't be end-to-end verified today (2026-09-06): the 2026 season hasn't
kicked off (season_start_date 2026-09-09), so a manual check of the "playing
now" view looks identical whether it's working or silently broken. This
pins the behavior against known + hypothetical status strings so it's
trustworthy the first time it matters.

Run: python -m tests.test_live_filter   (from lineup-view/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board import is_live  # noqa: E402


def test_known_not_live():
    for status in ("pre_game", "complete", "final", "postponed", "canceled", "cancelled", None, ""):
        assert not is_live(status), f"{status!r} should NOT be live"


def test_known_live():
    for status in ("in_game", "halftime", "delayed", "live", "in_progress"):
        assert is_live(status), f"{status!r} should be live"


if __name__ == "__main__":
    test_known_not_live()
    test_known_live()
    print("ok")
