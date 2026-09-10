"""Start/sit recommendation engine: given one league's full roster (mine
side) and its slot structure, recommend which players should be active and,
among flex-eligible players who are all going to start anyway, which
physical slot each should occupy -- putting whoever plays latest into the
most flexible slot (FLEX over a dedicated position, SUPER_FLEX over FLEX)
so the last actionable decision gets made with the most information, per
Simon's own heuristic: 2 RB slots + 1 FLEX, 3 RBs worth starting -> the RB
playing last goes in FLEX, not one of the two dedicated RB spots.

Reassigning slots among an already-decided starter set never changes total
points (Sleeper scores by is_starter, not by which slot someone's in) --
"who starts at all" and "which physical slot" are two separate passes below
for exactly that reason: the first is a points question (see _score), the
second a pure optionality question (see the position-group pass).

Slot-lock reality check: once a slot's CURRENT occupant's game has kicked
off, Sleeper won't let that slot be edited regardless of what an optimizer
would prefer -- so a locked slot's current player is fixed before either
pass runs, not just flagged afterward. See _is_locked.
"""
from typing import Optional

# Sleeper's own bench-like slot codes -- these appear in roster_positions
# but aren't part of the starting lineup, so they're dropped before either
# pass runs (matches board.py's own BENCH_SLOTS = {"BN", "IR"}, plus TAXI
# for dynasty leagues, which this app hasn't hit yet but roster_positions
# can legally include).
BENCH_LIKE = {"BN", "IR", "TAXI"}

# Slot eligibility, keyed by Sleeper's own roster_positions codes. Anything
# not listed here (a plain "QB"/"RB"/"WR"/"TE"/"DEF"/"K", or an IDP code this
# app doesn't otherwise support) falls back to "eligible for itself only" --
# see _slot_eligibility's fallback.
FLEX_ELIGIBILITY = {
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "WRTE_FLEX": {"WR", "TE"},
}

# Anything other than these counts as a real availability concern for
# picking who should start -- broader than an enumerated bad-list (PUP, IR,
# Out, Doubtful, Suspended, ... all show up in Sleeper's player dump, and a
# denylist would silently treat an unseen one as fine) rather than narrower.
OK_INJURY_STATUSES = {None, "Questionable", "Probable"}


def _slot_eligibility(slot: str) -> set:
    return FLEX_ELIGIBILITY.get(slot, {slot})


def _flexibility_rank(slot: str) -> int:
    """Higher = more positions can fill this slot = more valuable to keep
    open for the latest-arriving information. Nested by construction for
    every league shape this app's own leagues actually have (RB/WR/TE is a
    subset of FLEX's eligible set, which is a subset of SUPER_FLEX's) --
    that's what makes the greedy fill below correct. Not guaranteed globally
    optimal for a league that mixes two non-nested 2-way flexes (e.g.
    WRRB_FLEX and REC_FLEX in the same lineup) -- not worth an ILP for a
    case none of Simon's leagues have."""
    return len(_slot_eligibility(slot))


def _is_locked(a: Optional[dict]) -> bool:
    """A slot is locked once its occupant's game has kicked off -- Sleeper
    itself won't allow that slot to change at that point, independent of
    what this recommender would otherwise suggest."""
    return a is not None and a.get("game_status") not in (None, "pre_game")


def _eligible_positions(a: dict) -> set:
    # fantasy_positions is Sleeper's own multi-eligibility list (a player
    # who qualifies at more than one position) -- pos alone would wrongly
    # exclude those players from slots they can legally fill.
    fp = set(a.get("fantasy_positions") or [])
    return fp or {a.get("pos")}


def _score(a: dict) -> float:
    """Who to start, all else equal: highest blended points (board.py's
    `projected`, already actual-vs-projection blended), pushed to the
    bottom of the list -- but still selectable if nothing else fills the
    slot -- when hurt or apparently on bye."""
    proj = a.get("projected") or 0.0
    penalty = 0.0
    if a.get("injury_status") not in OK_INJURY_STATUSES:
        penalty -= 1000.0
    if a.get("game_status") is None:
        penalty -= 1000.0  # most likely a bye -- see board.py's schedule_by_team lookup
    return proj + penalty


def _kickoff_key(a: dict):
    k = a.get("kickoff")
    return k or ""  # ISO 8601 strings sort chronologically; missing sorts first (earliest)


def _slim(a: Optional[dict]) -> Optional[dict]:
    if not a:
        return None
    return {
        "player_id": a["player_id"],
        "name": a["name"],
        "pos": a["pos"],
        "team": a.get("team"),
        "points": a.get("points"),
        "projected": a.get("projected"),
        "kickoff": a.get("kickoff"),
        "game_status": a.get("game_status"),
        "injury_status": a.get("injury_status"),
    }


def recommend_lineup(roster: list, roster_positions: list, current_by_slot: list) -> dict:
    """roster: every rostered player on the mine side, starters and bench
    alike (board.py already builds one appearance dict per rostered player,
    not just starters).
    roster_positions: this league's full slot list, in Sleeper's own order,
    BN/IR/TAXI included.
    current_by_slot: one entry per NON-bench slot, same order as
    roster_positions with bench slots dropped, each the appearance dict
    currently occupying it or None. Relies on Sleeper's `starters` array
    being ordered to match roster_positions minus bench slots -- empirically
    verified against every league + week in .cache/ (see tests/test_lineup.py
    and board.py's build_appearances)."""
    starting_slots = [s for s in roster_positions if s not in BENCH_LIKE]
    if not starting_slots:
        return {"slots": [], "notes": []}

    assigned = {}
    used_ids = set()
    locked_idxs = set()

    for idx, cur in enumerate(current_by_slot):
        if idx < len(starting_slots) and _is_locked(cur):
            assigned[idx] = cur
            used_ids.add(cur["player_id"])
            locked_idxs.add(idx)

    open_idxs = [i for i in range(len(starting_slots)) if i not in locked_idxs]
    # Most-restrictive slots first (see _flexibility_rank) -- correct for the
    # nested flex families every league here actually has.
    open_idxs.sort(key=lambda i: _flexibility_rank(starting_slots[i]))

    for idx in open_idxs:
        elig = _slot_eligibility(starting_slots[idx])
        candidates = [a for a in roster
                      if a["player_id"] not in used_ids and (_eligible_positions(a) & elig)]
        if not candidates:
            continue
        best = max(candidates, key=_score)
        assigned[idx] = best
        used_ids.add(best["player_id"])

    # ---- optionality pass: same starters, reordered by kickoff into the
    # most flexible slot each is grouped with -- see module docstring. Only
    # ever permutes slots that already legally held that exact position, so
    # this can never produce an invalid (position-ineligible) assignment.
    by_pos: dict = {}
    for idx, a in assigned.items():
        if idx in locked_idxs:
            continue
        by_pos.setdefault(a["pos"], []).append(idx)

    for pos, idxs in by_pos.items():
        if len(idxs) < 2:
            continue
        if len({_flexibility_rank(starting_slots[i]) for i in idxs}) < 2:
            continue  # every slot in this group is equally flexible -- no decision to make
        ordered_slots = sorted(idxs, key=lambda i: -_flexibility_rank(starting_slots[i]))
        ordered_players = sorted((assigned[i] for i in idxs), key=_kickoff_key, reverse=True)
        for slot_idx, player in zip(ordered_slots, ordered_players):
            assigned[slot_idx] = player

    slots_out = []
    for idx, slot in enumerate(starting_slots):
        cur = current_by_slot[idx] if idx < len(current_by_slot) else None
        rec = assigned.get(idx)
        locked = idx in locked_idxs
        changed = bool((not locked) and (
            (cur is None) != (rec is None)
            or (cur is not None and rec is not None and cur["player_id"] != rec["player_id"])
        ))
        slots_out.append({
            "slot": slot,
            "current": _slim(cur),
            "recommended": _slim(rec),
            "locked": locked,
            "changed": changed,
        })

    # ---- notes: start/sit (a real points decision) worded separately from
    # a pure slot move (an optionality-only decision), so the two don't read
    # as the same kind of suggestion.
    notes = []
    current_ids = {a["player_id"] for a in current_by_slot if a}
    recommended_ids = {a["player_id"] for a in assigned.values() if a}
    by_id = {a["player_id"]: a for a in roster}

    for pid in sorted(recommended_ids - current_ids):
        a = by_id.get(pid)
        if a:
            notes.append(f"Start {a['name']} ({a['pos']}) — proj {a.get('projected') or 0:.1f}")
    for pid in sorted(current_ids - recommended_ids):
        a = by_id.get(pid)
        if a:
            notes.append(f"Sit {a['name']} ({a['pos']}) — proj {a.get('projected') or 0:.1f}")

    current_slot_of = {current_by_slot[i]["player_id"]: starting_slots[i]
                        for i in range(len(current_by_slot)) if current_by_slot[i]}
    recommended_slot_of = {a["player_id"]: starting_slots[i] for i, a in assigned.items() if a}
    for pid in sorted(recommended_ids & current_ids):
        old_slot = current_slot_of.get(pid)
        new_slot = recommended_slot_of.get(pid)
        if old_slot and new_slot and old_slot != new_slot:
            a = by_id.get(pid)
            notes.append(
                f"Move {a['name']} ({a['pos']}) from {old_slot} to {new_slot} — "
                f"plays last, keeps the most optionality if news breaks late"
            )

    return {"slots": slots_out, "notes": notes}
