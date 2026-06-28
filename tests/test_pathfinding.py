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