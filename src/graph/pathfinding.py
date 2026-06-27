"""Simple grid pathfinding for navigation."""

from __future__ import annotations

import heapq
from typing import Literal

Direction = Literal["up", "down", "left", "right"]


def _grid_from_rows(rows: list[str]) -> list[list[int]]:
    return [[int(c) for c in row] for row in rows]


# Simplified walkable grids for early-game maps (0=walkable, 1=blocked)
MAP_GRIDS: dict[str, list[list[int]]] = {
    "0:0": _grid_from_rows(
        [
            "00000000000000000000",
            "00000000000000000000",
            "00001111110000000000",
            "00001111110000000000",
            "00000000000000000000",
            "00000000000000000000",
        ]
    ),
    "1:1": _grid_from_rows(
        [
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
        ]
    ),
}


def _in_bounds(grid: list[list[int]], x: int, y: int) -> bool:
    return 0 <= y < len(grid) and 0 <= x < len(grid[0])


def _is_walkable(grid: list[list[int]] | None, x: int, y: int) -> bool:
    """Out-of-grid coordinates are walkable (open-world fallback)."""
    if grid is None:
        return True
    if not _in_bounds(grid, x, y):
        return True
    return grid[y][x] == 0


def direction_toward(start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    """Primary direction toward target; 'a' only when already at target."""
    if start_x == end_x and start_y == end_y:
        return "a"
    if end_x > start_x:
        return "right"
    if end_x < start_x:
        return "left"
    if end_y > start_y:
        return "down"
    if end_y < start_y:
        return "up"
    return "a"


def find_path(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    *,
    map_key: str = "",
    max_steps: int = 50,
) -> list[Direction]:
    """A* pathfinding on a collision grid. Returns list of directions."""
    if start_x == end_x and start_y == end_y:
        return []

    grid = MAP_GRIDS.get(map_key)
    open_set: list[tuple[int, int, int, list[Direction]]] = []
    heapq.heappush(open_set, (0, start_x, start_y, []))
    visited: set[tuple[int, int]] = {(start_x, start_y)}

    while open_set:
        _, x, y, path = heapq.heappop(open_set)
        if len(path) >= max_steps:
            return path

        for direction, dx, dy in [
            ("up", 0, -1),
            ("down", 0, 1),
            ("left", -1, 0),
            ("right", 1, 0),
        ]:
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited:
                continue
            if not _is_walkable(grid, nx, ny):
                continue
            new_path = path + [direction]  # type: ignore[list-item]
            if nx == end_x and ny == end_y:
                return new_path
            visited.add((nx, ny))
            h = abs(end_x - nx) + abs(end_y - ny)
            heapq.heappush(open_set, (h + len(new_path), nx, ny, new_path))

    return _greedy_directions(start_x, start_y, end_x, end_y, grid)


def _greedy_directions(
    x: int, y: int, tx: int, ty: int, grid: list[list[int]] | None
) -> list[Direction]:
    directions: list[Direction] = []
    cx, cy = x, y
    for _ in range(20):
        if cx == tx and cy == ty:
            break
        primary = direction_toward(cx, cy, tx, ty)
        if primary == "a":
            break
        candidates: list[Direction] = [primary]  # type: ignore[list-item]
        dx, dy = tx - cx, ty - cy
        if abs(dx) >= abs(dy):
            if dy > 0:
                candidates.append("down")
            elif dy < 0:
                candidates.append("up")
        else:
            if dx > 0:
                candidates.append("right")
            elif dx < 0:
                candidates.append("left")

        moved = False
        for d in candidates:
            ndx, ndy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
            nx, ny = cx + ndx, cy + ndy
            if _is_walkable(grid, nx, ny):
                directions.append(d)
                cx, cy = nx, ny
                moved = True
                break
        if not moved:
            break
    return directions


def direction_to_button(direction: Direction | str) -> str:
    return direction