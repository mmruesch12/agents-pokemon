"""Simple grid pathfinding for navigation."""

from __future__ import annotations

import heapq
from typing import Literal

Direction = Literal["up", "down", "left", "right"]


def _grid_from_rows(rows: list[str]) -> list[list[int]]:
    return [[int(c) for c in row] for row in rows]


# Warp-hint rows derived from MAP_GRIDS layout (control plane, not phase curriculum).
MAP_WARP_HINT_ROWS: dict[str, dict[str, int]] = {
    "24:4": {"east": 12},
    "24:3": {"north": 5},
    "26:1": {"north": 3},
}

# Simplified walkable grids for early-game maps (0=walkable, 1=blocked)
MAP_GRIDS: dict[str, list[list[int]]] = {
    "24:7": _grid_from_rows(
        [
            "11111110",
            "00111100",
            "00000000",
            "00000000",
            "10001100",
            "10000000",
            "00000000",
            "00000000",
        ]
    ),
    "24:6": _grid_from_rows(
        [
            "1111111110",  # stairs warp at (9,0)
            "1101111010",  # block west kitchen counter at (8,1)
            "0011111000",  # block counter column at (6,2) — not walkable in-game
            "0001011100",  # table at (3,3), (5,3); mom NPC at (7,3)
            "0000000100",  # block (7,4) — use x=8 corridor toward door
            "0000000000",
            "0000000000",
            "1111111100",  # front door warps at (6,7) and (7,7)
        ]
    ),
    "24:4": _grid_from_rows(
        [
            "00000000000000000000",  # y=0
            "00000000000000000000",  # y=1
            "00001111110000000000",  # y=2 lab/houses north; lab door (6,3)
            "00001111110000000000",  # y=3
            "00000000000000000000",  # y=4
            "00000000000000000000",  # y=5 house exit warp ~(13,5)
            "00000000000000000000",  # y=6 east corridor row
            "00000000000000000000",  # y=7
            "00000000000000000000",  # y=8 teacher gate west edge (1,8)/(1,9)
            "00000000000000000000",  # y=9 south corridor at x=17
            "00000000000001111100",  # y=10 south edge / cliff
            "00000000000001111100",  # y=11
            "00000000000000000000",  # y=12 route gate row; east exit ~(19,12)
            "00000000000000000000",  # y=13
        ]
    ),
    "24:5": _grid_from_rows(
        [
            "1111111111",  # y=0 desks
            "1110111111",  # y=1
            "0000000000",  # y=2 Elm at (5,2)
            "0000000000",  # y=3 balls at (6,3)/(7,3)/(8,3) — interact targets
            "0000000000",  # y=4
            "0000000000",  # y=5
            "0000110000",  # y=6 blocked exit (4,6)/(5,6) pre-starter
            "0000000000",  # y=7
            "0000000000",  # y=8 aide at (4,8)/(5,8)
            "0000000000",  # y=9
            "0000000000",  # y=10
            "0000110000",  # y=11 exit warp (4,11)/(5,11)
        ]
    ),
    "24:3": _grid_from_rows(
        [
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
        ]
    ),
    "26:1": _grid_from_rows(
        [
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
            "00000000000000000000",
        ]
    ),
    "26:10": _grid_from_rows(
        [
            "1111111111",
            "1000000001",
            "1000000001",
            "1000000001",
            "1000000001",
            "1000110001",  # Mr. Pokemon at (5,5)
            "1000000001",
            "1000000001",
            "1111111111",
        ]
    ),
}


def _in_bounds(grid: list[list[int]], x: int, y: int) -> bool:
    return 0 <= y < len(grid) and 0 <= x < len(grid[0])


def _is_walkable(
    grid: list[list[int]] | None,
    x: int,
    y: int,
    *,
    goal: tuple[int, int] | None = None,
) -> bool:
    """Walkable check; defined grids treat out-of-bounds as blocked."""
    if goal is not None and (x, y) == goal:
        return True
    if grid is None:
        return True
    if not _in_bounds(grid, x, y):
        return False
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
    goal = (end_x, end_y)
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
            if not _is_walkable(grid, nx, ny, goal=goal):
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
    goal = (tx, ty)
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
            if _is_walkable(grid, nx, ny, goal=goal):
                directions.append(d)
                cx, cy = nx, ny
                moved = True
                break
        if not moved:
            break
    return directions


def direction_to_button(direction: Direction | str) -> str:
    return direction