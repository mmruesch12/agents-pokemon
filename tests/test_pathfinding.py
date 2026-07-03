"""Tests for navigation pathfinding."""

from __future__ import annotations

from src.graph.pathfinding import (
    MAP_GRIDS,
    _is_walkable,
    direction_toward,
    direction_to_button,
    find_path,
    map_edge_exit_direction,
    record_session_blocked,
    session_blocked_for_map,
)
from src.state.models import GameState



def test_route_29_grid_covers_outdoor_coordinates():
    grid = MAP_GRIDS["24:3"]
    assert len(grid[0]) == 60
    assert len(grid) == 18
    assert _is_walkable(grid, 59, 8) is True
    assert _is_walkable(grid, 43, 8) is False


def test_find_path_route_29_ledge_detours_south():
    state: dict = {}
    record_session_blocked(state, "24:3", 43, 8)
    path = find_path(44, 8, 10, 5, map_key="24:3", state=state)
    assert path
    assert path[0] in {"down", "right", "up"}


def test_interact_tick_frames_uses_outdoor_ticks_between_sign_pages():
    from src.graph.nodes import OUTDOOR_INTERACT_TICKS, SCRIPT_WAIT_TICKS, _interact_tick_frames

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 38, "y": 14},
        in_text_box=False,
        raw_metadata={"script_mode": 1, "in_script": True},
    )
    assert _interact_tick_frames(gs) == OUTDOOR_INTERACT_TICKS

    indoor = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 3},
        in_text_box=True,
        raw_metadata={"in_script": True},
    )
    assert _interact_tick_frames(indoor) == SCRIPT_WAIT_TICKS


def test_exploration_biases_northwest_toward_route_30_gate():
    from src.graph.exploration import exploration_target

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 25, "y": 14},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = {
        "house_exit_complete": True,
        "active_subgoal": "Cross Route 29",
        "subgoals": ["Enter Route 29", "Cross Route 29", "Visit Mr. Pokemon's house"],
        "visited_positions": ["24:3:25:14"],
    }
    target = exploration_target(gs, state, hint_tile=(10, 5))
    assert target[0] < gs.player.x or target[1] < gs.player.y


def test_exploration_target_skips_unreachable_landmark(monkeypatch):
    from src.graph import exploration as exploration_mod
    from src.graph.exploration import exploration_target

    monkeypatch.setattr(exploration_mod, "find_path", lambda *a, **k: [])

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 44, "y": 8},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state: dict = {}
    target = exploration_target(gs, state, hint_tile=(10, 5))
    assert target != (10, 5)


def test_find_path_same_position():
    assert find_path(5, 5, 5, 5) == []


def test_find_path_simple():
    path = find_path(0, 0, 3, 0, map_key="")
    assert len(path) == 3
    assert all(d == "right" for d in path)


def test_session_walkable_does_not_override_static_blocked():
    from src.graph.pathfinding import session_walkable_for_map

    state = {"session_walkable": {"24:4": [(13, 11)]}}
    session = session_walkable_for_map(state, "24:4")
    assert _is_walkable(MAP_GRIDS["24:4"], 13, 11, session_walkable=session) is False


def test_exploration_nb_west_row_without_landmark():
    from src.graph.exploration import exploration_target

    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 9, "y": 8})
    state = {"house_exit_complete": True, "active_subgoal": "Enter Route 29"}
    record_session_blocked(state, "24:4", 8, 8)
    target = exploration_target(gs, state)
    assert target[1] == 8
    assert target[0] < gs.player.x


def test_find_path_new_bark_blocked_west_stays_on_row():
    state: dict = {}
    record_session_blocked(state, "24:4", 10, 8)
    path = find_path(9, 8, 0, 8, map_key="24:4", state=state)
    assert path
    assert path[0] == "left"
    positions = _positions_after(9, 8, path)
    assert (10, 8) not in positions
    assert all(y == 8 for x, y in positions[:3])


def test_find_path_new_bark_east_corridor():
    """New Bark grid covers y=12; eastward path along the corridor row."""
    path = find_path(8, 12, 10, 12, map_key="24:4")
    assert len(path) >= 1
    assert path[0] == "right"
    state: dict = {}
    record_session_blocked(state, "24:4", 6, 8)
    assert session_blocked_for_map(state, "24:4") == {(6, 8)}
    blocked_path = find_path(6, 7, 0, 8, map_key="24:4", state=state)
    assert blocked_path
    assert blocked_path[0] != "down"
    blocked = session_blocked_for_map(state, "24:4")
    assert _is_walkable(None, 6, 8, session_blocked=blocked) is False
    assert (
        _is_walkable(None, 6, 8, goal=(6, 8), session_blocked=blocked) is False
    )


def test_find_path_new_bark_south_blocked_at_cliff():
    """South from (17,9) is blocked in the 24:4 grid (no infinite fallback)."""
    path = find_path(17, 9, 17, 11, map_key="24:4")
    assert path == [] or path[-1] != "down" or len(path) < 2


def test_direction_toward_new_bark():
    assert direction_toward(8, 12, 10, 12) == "right"
    assert direction_toward(10, 12, 10, 12) == "a"


def test_find_path_with_obstacles():
    path = find_path(0, 0, 5, 0, map_key="24:4")
    assert len(path) > 0
    assert path[-1] in ("up", "down", "left", "right")


def test_direction_to_button():
    assert direction_to_button("up") == "up"
    assert direction_to_button("right") == "right"


def test_find_path_players_house_toward_stairs():
    path = find_path(3, 3, 7, 0, map_key="24:7")
    assert len(path) >= 2
    assert path[0] in ("up", "right")


def test_find_path_players_house_1f_to_front_door():
    """Door warp tiles are blocked in the grid but must remain valid goals."""
    path = find_path(9, 1, 6, 7, map_key="24:6")
    assert len(path) >= 5
    assert path[0] == "down"
    assert path[-1] == "down"


def test_elms_lab_ball_tiles_blocked_in_grid():
    """Ball object columns 6-8 on y=3 are blocked unless explicitly the path goal."""
    from src.graph.pathfinding import MAP_GRIDS

    grid = MAP_GRIDS["24:5"]
    for bx in (6, 7, 8):
        assert grid[3][bx] == 1
    path = find_path(4, 2, 5, 3, map_key="24:5")
    ball_tiles = ((6, 3), (7, 3), (8, 3))
    assert all(pos not in ball_tiles for pos in _positions_after(4, 2, path))


def test_elms_lab_desk_to_ball_approach_avoids_elm():
    """From Elm's desk (4,2) route to (5,3) goes down around Elm at (5,2)."""
    path = find_path(4, 2, 5, 3, map_key="24:5")
    assert path
    assert path[0] == "down"
    assert "right" in path


def test_map_edge_exit_direction_at_west_edge_and_approach():
    gs_edge = GameState(
        player={"map_group": 24, "map_id": 4, "x": 0, "y": 8},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    gs_approach = GameState(
        player={"map_group": 24, "map_id": 4, "x": 1, "y": 8},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    assert map_edge_exit_direction(gs_edge, heading_west=True) == "left"
    assert map_edge_exit_direction(gs_approach, heading_west=True) == "left"
    assert map_edge_exit_direction(gs_edge, heading_west=False) is None


def test_navigator_at_west_edge_forces_left():
    from src.graph.nodes import navigator_node
    from src.graph.state import initial_agent_state
    from src.memory.landmarks import seed_static_map_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 0, "y": 8},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["active_subgoal"] = "Enter Route 29"
    state["subgoals"] = ["Enter Route 29", "Cross Route 29"]
    seed_static_map_landmarks(state)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_left"


def _positions_after(sx: int, sy: int, path: list[str]) -> list[tuple[int, int]]:
    x, y = sx, sy
    out: list[tuple[int, int]] = []
    for step in path:
        if step == "right":
            x += 1
        elif step == "left":
            x -= 1
        elif step == "up":
            y -= 1
        elif step == "down":
            y += 1
        out.append((x, y))
    return out