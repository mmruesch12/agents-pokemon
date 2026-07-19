"""ROM-free tests for Route 29 ledge pathing and corridor snapshot seeding."""

from __future__ import annotations

from src.emulator.bootstrap import seed_corridor_agent_state, seed_route_29_agent_state
from src.graph.pathfinding import (
    MAP_LANDMARK_ANCHORS,
    ROUTE_29_Y14_CLIMB_X,
    _directional_step_allowed,
    find_path,
)
from src.graph.state import initial_agent_state
from src.state.models import GameState


def test_route_29_sign_pocket_cannot_climb_except_at_gaps():
    assert _directional_step_allowed("24:3", 15, 14, 15, 13) is False
    assert _directional_step_allowed("24:3", 18, 14, 18, 13) is False
    for x in ROUTE_29_Y14_CLIMB_X:
        assert _directional_step_allowed("24:3", x, 14, x, 13) is True


def test_find_path_from_sign_pocket_goes_east_to_climb():
    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    path = find_path(15, 14, gate[0], gate[1], map_key="24:3")
    assert path
    assert path[0] == "right"
    # Must use a climb (up from y=14 at a climb x) rather than false-up at x=15.
    x, y = 15, 14
    climbed = False
    for step in path:
        if step == "up" and y == 14:
            assert x in ROUTE_29_Y14_CLIMB_X
            climbed = True
            break
        if step == "right":
            x += 1
        elif step == "left":
            x -= 1
        elif step == "down":
            y += 1
        elif step == "up":
            y -= 1
    assert climbed


def test_find_path_from_gate_approach_drops_south_then_climbs():
    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    path = find_path(24, 10, gate[0], gate[1], map_key="24:3")
    assert path
    assert path[0] == "down"
    assert "up" in path  # climb after south corridor


def test_seed_corridor_cherrygrove_marks_house_and_starter_progress():
    gs = GameState(
        player={"map_group": 26, "map_id": 3, "x": 39, "y": 7},
        raw_metadata={"has_starter": True, "mom_scene_complete": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    seeded = seed_corridor_agent_state(state, gs)
    assert seeded["house_exit_complete"] is True
    assert seeded["bootstrap_complete"] is True
    assert "Reached Cherrygrove City" in seeded["milestones"]
    assert "Reached Route 29" in seeded["milestones"]


def test_seed_corridor_violet_city_targets_gym_entrance():
    gs = GameState(
        player={"map_group": 10, "map_id": 5, "x": 18, "y": 18},
        raw_metadata={"has_starter": True, "egg_delivered": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    seeded = seed_corridor_agent_state(state, gs)
    assert seeded["starter_quest_complete"] is True
    assert seeded["active_subgoal"] == "Find Violet Gym entrance"
    assert "Reached Violet City" in seeded["milestones"]


def test_seed_corridor_violet_gym_targets_falkner_not_entrance():
    gs = GameState(
        player={"map_group": 10, "map_id": 7, "x": 4, "y": 15},
        raw_metadata={"has_starter": True, "egg_delivered": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    seeded = seed_corridor_agent_state(state, gs)
    assert seeded["early_progression_complete"] is True
    assert seeded["active_subgoal"] == "Challenge Falkner (first gym reached)"
    assert "Entered Violet Gym" in seeded["milestones"]


def test_route_30_west_path_reaches_route_31_gate():
    """Live R30: west corridor reaches north edge (6,0); east mid does not short-cut."""
    path = find_path(5, 30, 6, 0, map_key="26:1")
    assert path
    assert len(path) >= 20
    # East of the mid barrier should not have a 1–5 step false path to the gate.
    short = find_path(16, 7, 6, 0, map_key="26:1")
    if short:
        assert len(short) > 10


def test_route_30_mid_east_path_false_left_blocked_reaches_gate():
    """From (12,12) A* must not start left into wall; must reach (6,0) via south/west."""
    path = find_path(12, 12, 6, 0, map_key="26:1", max_steps=250)
    assert path
    assert len(path) > 20
    assert path[0] != "left"  # live left from (12,12) is solid
    x, y = 12, 12
    for step in path:
        if step == "left":
            x -= 1
        elif step == "right":
            x += 1
        elif step == "up":
            y -= 1
        elif step == "down":
            y += 1
    assert (x, y) == (6, 0)
    # Live BFS joins west around y24–30; path should go that deep south first.
    assert path.count("down") >= 10


def test_seed_route_29_still_used_on_route_29_snapshot():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 24, "y": 10},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    seeded = seed_route_29_agent_state(state, gs)
    assert seeded["house_exit_complete"] is True
    assert "Reached Route 29" in seeded["milestones"]


def test_route_30_y48_north_only_at_gap():
    assert _directional_step_allowed("26:1", 10, 48, 10, 47) is False
    assert _directional_step_allowed("26:1", 12, 48, 12, 47) is True
    # Climb gap is x=12; target Mr. Pokemon door (17,5) via east corridor.
    path = find_path(10, 48, 17, 5, map_key="26:1")
    assert path
    # Must move horizontally before climbing the y=48 gap.
    assert path[0] in ("left", "right")


def test_route_30_egg_return_from_east_pocket_avoids_false_down():
    """Live: (9,8) is solid; egg-return A* must not pure-down thrash at (9,7)."""
    path = find_path(9, 7, 6, 53, map_key="26:1", max_steps=200)
    assert path
    assert len(path) >= 40
    # First step must leave the false vertical (right/left), not down into wall.
    assert path[0] in ("right", "left", "up")
    # Path must eventually go south to Cherry edge.
    assert path.count("down") >= 20


def test_route_30_egg_return_from_mr_pokemon_door():
    path = find_path(17, 5, 6, 53, map_key="26:1", max_steps=200)
    assert path
    assert len(path) >= 40


def test_cherrygrove_path_from_east_entry_reaches_north_exit():
    """ROM grid: east entry must go west before north funnel (not blocked at y=6)."""
    north = MAP_LANDMARK_ANCHORS["26:3"]["north_exit"]
    path = find_path(39, 7, north[0], north[1], map_key="26:3")
    assert path
    assert path[0] == "left"
    # Simulate path stays on grid
    x, y = 39, 7
    for step in path:
        if step == "left":
            x -= 1
        elif step == "right":
            x += 1
        elif step == "up":
            y -= 1
        elif step == "down":
            y += 1
    assert (x, y) == north
