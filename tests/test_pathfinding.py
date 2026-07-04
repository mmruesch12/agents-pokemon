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


def test_find_path_route_29_gate_approach_prefers_south_corridor():
    path = find_path(24, 10, 14, 14, map_key="24:3")
    assert path
    assert path[0] == "down"
    assert "left" in path


def test_find_path_route_29_west_entrance_goes_north_to_gate():
    path = find_path(10, 12, 10, 5, map_key="24:3")
    assert path
    assert path[0] == "up"
    assert "right" not in path[:4]


def test_route_29_gate_waypoint_east_reentry_from_west_corridor():
    from src.graph.navigation_resolve import (
        ROUTE_29_CORRIDOR_EAST_REENTRY,
        _route_29_gate_south_corridor_waypoint,
    )

    for x in (14, 15, 20):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": x, "y": 14},
            party_count=1,
        )
        assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == (
            ROUTE_29_CORRIDOR_EAST_REENTRY
        )

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 22, "y": 15},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == (
        ROUTE_29_CORRIDOR_EAST_REENTRY
    )

    from src.graph.navigation_resolve import (
        ROUTE_29_LEDGE_CLIMB,
        ROUTE_29_LEDGE_CONNECTOR,
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 22, "y": 14},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == (
        ROUTE_29_LEDGE_CLIMB
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 23, "y": 11},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == (
        ROUTE_29_LEDGE_CONNECTOR
    )

    from src.graph.navigation_resolve import ROUTE_29_LEDGE_WEST_DESCENT

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 27, "y": 10},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == (
        ROUTE_29_LEDGE_WEST_DESCENT
    )


def test_route_29_gate_waypoint_gate_approach_column_routes_ledge_then_gate():
    from src.graph.navigation_resolve import (
        ROUTE_29_LEDGE_CONNECTOR,
        ROUTE_29_SOUTH_CORRIDOR,
        _route_29_gate_south_corridor_waypoint,
    )

    gate = (10, 5)
    for y in (10, 11):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": 24, "y": y},
            party_count=1,
        )
        assert _route_29_gate_south_corridor_waypoint(gs, gate, {}) == ROUTE_29_LEDGE_CONNECTOR
    for y in (12, 13):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": 24, "y": y},
            party_count=1,
        )
        assert _route_29_gate_south_corridor_waypoint(gs, gate, {}) == gate
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 24, "y": 14},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs, gate, {}) == ROUTE_29_SOUTH_CORRIDOR


def test_route_29_gate_waypoint_prefers_ledge_from_gate_approach():
    from src.graph.navigation_resolve import (
        ROUTE_29_LEDGE_CONNECTOR,
        _route_29_gate_south_corridor_waypoint,
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 24, "y": 10},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == ROUTE_29_LEDGE_CONNECTOR


def test_route_29_gate_waypoint_east_ledge_dead_end_uses_south_corridor():
    from src.graph.navigation_resolve import (
        ROUTE_29_SOUTH_CORRIDOR,
        _route_29_gate_south_corridor_waypoint,
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 44, "y": 10},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), {}) == ROUTE_29_SOUTH_CORRIDOR


def test_route_29_gate_waypoint_post_west_descent_uses_gate_approach_row():
    from src.graph.navigation_resolve import (
        ROUTE_29_WEST_GATE_APPROACH,
        _route_29_gate_south_corridor_waypoint,
    )
    from src.graph.pathfinding import record_session_walkable

    state: dict = {}
    for tile in ((23, 11), (27, 10), (25, 10), (25, 11)):
        record_session_walkable(state, "24:3", *tile)
    gs_mid_corridor = GameState(
        player={"map_group": 24, "map_id": 3, "x": 23, "y": 12},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs_mid_corridor, (10, 5), state) == (
        ROUTE_29_WEST_GATE_APPROACH
    )

    gs_at_descent = GameState(
        player={"map_group": 24, "map_id": 3, "x": 25, "y": 11},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs_at_descent, (10, 5), state) == (
        ROUTE_29_WEST_GATE_APPROACH
    )

    gs_post_ledge = GameState(
        player={"map_group": 24, "map_id": 3, "x": 27, "y": 11},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs_post_ledge, (10, 5), {}) == (
        ROUTE_29_WEST_GATE_APPROACH
    )

    gs_on_gate_column = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 11},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs_on_gate_column, (10, 5), state) == (
        10,
        5,
    )

    gate = (10, 5)
    for x, y in ((21, 14), (22, 14), (22, 15), (25, 13), (25, 14), (25, 15)):
        gs_corridor = GameState(
            player={"map_group": 24, "map_id": 3, "x": x, "y": y},
            party_count=1,
        )
        waypoint = _route_29_gate_south_corridor_waypoint(gs_corridor, gate, state)
        assert waypoint in (ROUTE_29_WEST_GATE_APPROACH, gate)


def test_find_path_post_west_descent_prefers_south_then_west_corridor():
    from src.graph.pathfinding import record_session_walkable

    state: dict = {}
    for tile in ((23, 11), (27, 10), (25, 10), (25, 11)):
        record_session_walkable(state, "24:3", *tile)
    path = find_path(25, 11, 10, 5, map_key="24:3", state=state)
    assert path
    assert path[0] == "down"
    west_row = find_path(25, 11, 10, 12, map_key="24:3", state=state)
    assert west_row
    assert west_row[0] == "down"


def test_route_29_grid_blocks_sign_tile():
    grid = MAP_GRIDS["24:3"]
    assert _is_walkable(grid, 25, 10) is True
    assert _is_walkable(grid, 38, 14) is False
    assert _is_walkable(grid, 42, 14) is False
    assert _is_walkable(grid, 13, 14) is False
    assert _is_walkable(grid, 14, 14) is True
    assert _is_walkable(grid, 22, 12) is False


def test_find_path_route_29_sign_pocket_avoids_west_on_y14():
    path = find_path(14, 14, 10, 5, map_key="24:3")
    assert path
    assert path[0] != "left"
    assert path[0] != "down" or path.count("right") > 0


def test_route_29_gate_waypoint_sign_pocket_y15_routes_to_west_corridor():
    from src.graph.navigation_resolve import (
        ROUTE_29_WEST_GATE_APPROACH,
        _route_29_gate_south_corridor_waypoint,
    )
    from src.graph.pathfinding import record_session_walkable

    state: dict = {}
    for tile in ((23, 11), (27, 10), (25, 10), (25, 11)):
        record_session_walkable(state, "24:3", *tile)
    for x, y in ((15, 15), (16, 15)):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": x, "y": y},
            party_count=1,
        )
        assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), state) == (
            ROUTE_29_WEST_GATE_APPROACH
        )


def test_route_29_gate_waypoint_sign_pocket_routes_to_west_corridor():
    from src.graph.navigation_resolve import (
        ROUTE_29_WEST_GATE_APPROACH,
        _route_29_gate_south_corridor_waypoint,
    )
    from src.graph.pathfinding import record_session_walkable

    state: dict = {}
    for tile in ((23, 11), (27, 10), (25, 10), (25, 11)):
        record_session_walkable(state, "24:3", *tile)
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 14, "y": 14},
        party_count=1,
    )
    assert _route_29_gate_south_corridor_waypoint(gs, (10, 5), state) == (
        ROUTE_29_WEST_GATE_APPROACH
    )


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