"""Tests for navigation pathfinding."""

from __future__ import annotations

from src.graph.pathfinding import direction_toward, find_path, direction_to_button


def test_find_path_same_position():
    assert find_path(5, 5, 5, 5) == []


def test_find_path_simple():
    path = find_path(0, 0, 3, 0, map_key="")
    assert len(path) == 3
    assert all(d == "right" for d in path)


def test_find_path_out_of_grid_bounds():
    """New Bark fixture coords (8,12) are outside the 6-row grid — must still move."""
    path = find_path(8, 12, 10, 12, map_key="0:0")
    assert len(path) >= 1
    assert path[0] == "right"


def test_direction_toward_new_bark():
    assert direction_toward(8, 12, 10, 12) == "right"
    assert direction_toward(10, 12, 10, 12) == "a"


def test_find_path_with_obstacles():
    path = find_path(0, 0, 5, 0, map_key="0:0")
    assert len(path) > 0
    assert path[-1] in ("up", "down", "left", "right")


def test_direction_to_button():
    assert direction_to_button("up") == "up"
    assert direction_to_button("right") == "right"


def test_find_path_players_house_direct_south():
    path = find_path(3, 1, 3, 3, map_key="3:4")
    assert path == ["down", "down"]