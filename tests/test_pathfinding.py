"""Tests for navigation pathfinding."""

from __future__ import annotations

from src.graph.pathfinding import direction_toward, find_path, direction_to_button



def test_find_path_same_position():
    assert find_path(5, 5, 5, 5) == []


def test_find_path_simple():
    path = find_path(0, 0, 3, 0, map_key="")
    assert len(path) == 3
    assert all(d == "right" for d in path)


def test_find_path_new_bark_east_corridor():
    """New Bark grid covers y=12; eastward path along the corridor row."""
    path = find_path(8, 12, 10, 12, map_key="24:4")
    assert len(path) >= 1
    assert path[0] == "right"


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