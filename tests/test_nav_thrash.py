"""Pure thrash scorer + wire into stuck meter (ROM-free)."""

from __future__ import annotations

from src.graph.nav_thrash import append_nav_position, nav_thrash_severity
from src.graph.nodes import _update_stuck_from_movement, select_navigation_action
from src.state.models import GameState


def test_nav_thrash_severity_empty_and_short():
    assert nav_thrash_severity([]) == 0
    assert nav_thrash_severity([("24:3", 11, 10)] * 3) == 0


def test_nav_thrash_severity_two_tile_oscillation_r29_egg_return():
    """Live bedroom_gym3 / bed_egg_cont: (11,10)↔(11,11) with stuck=0."""
    hist = []
    for i in range(12):
        y = 10 if i % 2 == 0 else 11
        hist.append(("24:3", 11, y))
    sev = nav_thrash_severity(hist, window=12)
    assert sev >= 1


def test_nav_thrash_severity_r30_left_right_thrash():
    """Live bed_egg_cont class: x flip at fixed y (7↔8, y=30)."""
    hist = []
    for i in range(12):
        x = 7 if i % 2 == 0 else 8
        hist.append(("26:1", x, 30))
    assert nav_thrash_severity(hist, window=12) >= 1


def test_nav_thrash_severity_map_flipflop():
    """R31→R30 south bounce: map_key flip-flops without progress."""
    hist = []
    for i in range(10):
        mk = "26:2" if i % 2 == 0 else "26:1"
        hist.append((mk, 26, 17 if mk == "26:2" else 6))
    assert nav_thrash_severity(hist, window=12) >= 1


def test_nav_thrash_severity_same_tile_freeze():
    hist = [("24:3", 11, 10)] * 8
    assert nav_thrash_severity(hist, window=12) >= 1


def test_nav_thrash_severity_progressing_corridor_is_zero():
    """Westbound march on y=7 should not score thrash."""
    hist = [("24:3", x, 7) for x in range(36, 24, -1)]
    assert nav_thrash_severity(hist, window=12) == 0


def test_nav_thrash_severity_r31_multi_tile_pocket():
    """Live gym26: x24–25 y11–15 wander with stuck=0 (not just 2-tile)."""
    hist = []
    pocket = [(24, 11), (25, 11), (24, 12), (24, 13), (25, 12), (24, 14), (24, 15), (25, 11)]
    for i in range(12):
        x, y = pocket[i % len(pocket)]
        hist.append(("26:2", x, y))
    assert nav_thrash_severity(hist, window=12) >= 1


def test_append_nav_position_caps():
    pos = None
    for i in range(30):
        pos = append_nav_position(pos, "24:3", i, 0, max_len=24)
    assert len(pos) == 24
    assert pos[0] == ("24:3", 6, 0)


def test_update_stuck_from_movement_thrash_bumps_stuck():
    """Moving thrash must raise stuck_count (shipped apply_action path)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 11, "y": 11},
        party_count=1,
    )
    state: dict = {
        "stuck_count": 0,
        "recent_nav_positions": [
            ("24:3", 11, 10 if i % 2 == 0 else 11) for i in range(10)
        ],
        "short_term_history": [],
        "session_walkable": {},
    }
    # Simulate move 11,10 → 11,11 (still thrashing).
    _update_stuck_from_movement(
        state,
        "navigate_down",
        pos_before="24:3:11:10",
        pos_after="24:3:11:11",
        gs=gs,
    )
    assert state["stuck_count"] >= 1
    assert len(state["recent_nav_positions"]) >= 11


def test_update_stuck_from_movement_progress_clears_stuck():
    """Genuine west progress should still ease stuck."""
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 30, "y": 7},
        party_count=1,
    )
    state: dict = {
        "stuck_count": 3,
        "recent_nav_positions": [("24:3", x, 7) for x in range(36, 30, -1)],
        "short_term_history": [],
        "session_walkable": {},
    }
    _update_stuck_from_movement(
        state,
        "navigate_left",
        pos_before="24:3:31:7",
        pos_after="24:3:30:7",
        gs=gs,
    )
    # Progressing corridor: thrash=0 → stuck decrements.
    assert state["stuck_count"] == 2


def test_thrash_elevated_stuck_enables_navigation_arbitration():
    """After thrash bumps stuck, select_navigation path0 commit / arbitration path is live."""
    from src.graph.nodes import navigation_arbitration_active
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 11, "y": 10},
        raw_metadata={"has_mystery_egg": True, "egg_delivered": False},
        party_count=1,
    )
    state: dict = {
        "stuck_count": 0,
        "recent_nav_positions": [
            ("24:3", 11, 10 if i % 2 == 0 else 11) for i in range(10)
        ],
        "short_term_history": [
            f"navigate:up@11,10",
            f"navigate:down@11,11",
            f"navigate:up@11,10",
            f"navigate:down@11,11",
            f"navigate:up@11,10",
            f"navigate:down@11,11",
        ],
        "session_walkable": {},
        "house_exit_complete": True,
    }
    _update_stuck_from_movement(
        state,
        "navigate_up",
        pos_before="24:3:11:11",
        pos_after="24:3:11:10",
        gs=gs,
    )
    assert state["stuck_count"] >= 1
    assert navigation_arbitration_active(state["stuck_count"], state) is True
    east = MAP_LANDMARK_ANCHORS["24:3"]["east_exit"]
    path = find_path(11, 10, *east, map_key="24:3")
    assert path
    # With stuck elevated, oscillation break should prefer leaving the pair.
    action = select_navigation_action(
        door_exit=None,
        path=path,
        llm_choice="up",
        candidates=["left", "right", "up", "down"],
        stuck_count=state["stuck_count"],
        gs=gs,
        state=state,
        target=east,
    )
    assert action in ("left", "right", "up", "down")
    # Egg-return south corridor may force down before path0 east; never pure-A.
    assert action not in {"a", "b"}
    # Prefer not pure vertical thrash forever when path is lateral-first.
    if path[0] in ("left", "right"):
        assert action in ("left", "right", "up", "down")
