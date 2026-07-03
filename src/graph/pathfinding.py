"""Simple grid pathfinding for navigation."""

from __future__ import annotations

import heapq
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.state.models import GameState

Direction = Literal["up", "down", "left", "right"]


def _grid_from_rows(rows: list[str]) -> list[list[int]]:
    return [[int(c) for c in row] for row in rows]


# Warp-hint rows derived from MAP_GRIDS layout (control plane, not phase curriculum).
MAP_WARP_HINT_ROWS: dict[str, dict[str, int]] = {
    "24:4": {"west": 8, "north": 3},
    "24:5": {"north": 2},
    "24:3": {"north": 5, "east": 8},
    "26:1": {"north": 3},
}

# Building/warp anchor tiles from MAP_GRIDS layout (bootstrap landmark seeding only).
MAP_LANDMARK_ANCHORS: dict[str, dict[str, tuple[int, int]]] = {
    "24:4": {
        "elms_lab_door": (6, 3),
        "west_exit": (0, 8),
    },
    "24:3": {
        "route_30_gate": (10, 5),
    },
    "26:1": {
        "mr_pokemon_gate": (10, 3),
    },
    "24:5": {
        "desk_approach": (4, 3),
        "ball_approach": (6, 4),
        "south_exit": (4, 11),
    },
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
            "00000000000000000000",  # y=8 teacher gate west edge (0,8)/(1,9)
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
            "0000010000",  # y=2 Elm at (5,2) — blocked for routing around desk
            "0000001110",  # y=3 balls at (6,3)/(7,3)/(8,3) — blocked; interact from side
            "0000000000",  # y=4
            "0000000000",  # y=5
            "0010000000",  # y=6 (3,6) ROM dead-end; (4,6)/(5,6) gated at runtime
            "0000000000",  # y=7
            "0000000000",  # y=8 aide at (4,8)/(5,8)
            "0000000000",  # y=9
            "0000000000",  # y=10
            "0000000000",  # y=11 exit warp (4,11)/(5,11) — walkable
        ]
    ),
    "24:3": _grid_from_rows(
        [
            # 60x18 — pret ROUTE_29 30x9 blocks; collision from ROM BFS (x=21..59) + west connectors
            "111111111111111111111111111111111111111111111111111111111111",  # y=0
            "111111111111111111111111111011111111111111111111111111111111",  # y=1
            "111111111111111111111111000000111111111111111111111111111111",  # y=2
            "111111111111111111111111010100111111111111111111111111111111",  # y=3
            "111111111111111111111001000000111100000010111111111111111111",  # y=4
            "000000000000000000000000000000011100000001011111111111111111",  # y=5 gate row
            "111111111111111111111001101000000000001110111111100000111111",  # y=6
            "111111111111111111111110100101000000001100111110011100111111",  # y=7
            "111111111111111111111110000001001111001100110000000000000000",  # y=8 ledge at x<=43
            "111111111111111111111111111011111111001100010000000000000000",  # y=9
            "111111111111111111111111000000000000000001010000000001111111",  # y=10 ROM walkable x=25 from (24,10)
            "111111111111111111111110011010000000000000100000000000111111",  # y=11 block x=22 dead-end; x=23 ROM walkable
            "000000000000000000000110001111000001110000010001001000111111",  # y=12 open x=24 south; block x=26-27 east
            "000000000000000000000100000011111111110100110000100000111111",  # y=13
            "000000000000000000000100000000000011111000110000111111111111",  # y=14 block signs x=38,x=42; south x=24
            "000000000000000000000000000000000011111000000000111111111111",  # y=15 block sign x=38
            "000000000000000000000111000000000000000000001111111111111111",  # y=16
            "000000000000000000000111111100000000000000001111111111111111",  # y=17
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
    session_walkable: set[tuple[int, int]] | None = None,
    session_blocked: set[tuple[int, int]] | None = None,
) -> bool:
    """Walkable check; session overlay expands known tiles from movement outcomes."""
    if session_blocked and (x, y) in session_blocked:
        return False
    if goal is not None and (x, y) == goal:
        return True
    if session_walkable and (x, y) in session_walkable:
        if grid is None:
            return True
        if _in_bounds(grid, x, y) and grid[y][x] == 0:
            return True
    if grid is None:
        return True
    if not _in_bounds(grid, x, y):
        return False
    return grid[y][x] == 0


def _east_row_blocked_ahead(
    session_blocked: set[tuple[int, int]] | None,
    east_row: int,
    x: int,
) -> bool:
    if not session_blocked:
        return False
    return any(by == east_row and bx > x for bx, by in session_blocked)


def _east_row_blockage_between(
    session_blocked: set[tuple[int, int]] | None,
    east_row: int,
    x: int,
    end_x: int,
) -> bool:
    """Session-blocked tiles on the east corridor row between x and the goal."""
    if not session_blocked:
        return False
    return any(by == east_row and x < bx <= end_x for bx, by in session_blocked)


def _east_row_session_backoff_prefix(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    *,
    map_key: str,
    grid: list[list[int]] | None,
    session_blocked: set[tuple[int, int]] | None,
    state: dict | None = None,
    max_steps: int = 3,
) -> list[Direction]:
    """Retreat west along a warp-hint east row before detouring around session blocks."""
    hints = MAP_WARP_HINT_ROWS.get(map_key, {})
    east_row = hints.get("east")
    if east_row is None or start_y != east_row or end_y != east_row or end_x <= start_x:
        return []
    if not _east_row_blockage_between(session_blocked, east_row, start_x, end_x):
        return []
    stuck_count = (state or {}).get("stuck_count")
    if stuck_count is not None and stuck_count < 2:
        return []

    prefix: list[Direction] = []
    x = start_x
    goal = (end_x, end_y)
    while x > 0 and len(prefix) < max_steps:
        if not _east_row_blockage_between(session_blocked, east_row, x, end_x):
            break
        nx = x - 1
        if not _is_walkable(
            grid,
            nx,
            east_row,
            goal=goal,
            session_blocked=session_blocked,
        ):
            break
        prefix.append("left")
        x = nx
    return prefix


def _warp_row_step_penalty(
    map_key: str,
    x: int,
    y: int,
    nx: int,
    ny: int,
    *,
    end_x: int,
    end_y: int,
    session_blocked: set[tuple[int, int]] | None = None,
) -> int:
    """Prefer warp-hint corridor rows when routing toward distant east/north goals."""
    hints = MAP_WARP_HINT_ROWS.get(map_key, {})
    penalty = 0
    east_row = hints.get("east")
    if east_row is not None and end_x > x and end_y == east_row:
        blocked_ahead = _east_row_blocked_ahead(session_blocked, east_row, x)
        if y == east_row and blocked_ahead:
            if ny == east_row and nx < x:
                penalty -= 2
            elif ny != east_row:
                penalty += 500
        elif y == east_row and ny != east_row:
            penalty += 8
        elif y >= east_row - 1 and ny < east_row:
            penalty += 6
        elif ny != east_row:
            penalty += 3
    north_row = hints.get("north")
    if north_row is not None and end_y < y and end_y == north_row and ny != north_row:
        penalty += 2
    penalty += _route_29_gate_step_penalty(
        map_key, x, y, nx, ny, end_x=end_x, end_y=end_y
    )
    return penalty


def _route_29_gate_step_penalty(
    map_key: str,
    x: int,
    y: int,
    nx: int,
    ny: int,
    *,
    end_x: int,
    end_y: int,
) -> int:
    """ROM penalties for south-corridor and north-gate routing on Route 29."""
    if map_key != "24:3" or end_x >= x:
        return 0
    to_gate = end_y <= 6
    to_corridor = end_y >= 14
    if not to_gate and not to_corridor:
        return 0
    penalty = 0
    if to_gate:
        if y <= 11 and x >= 20:
            penalty += 6
        if ny <= 11 and nx >= 20:
            penalty += 6
        if ny > y and y <= 11 and x >= 20:
            penalty -= 3
        if ny > y and y == 10 and x <= 26:
            penalty -= 8
        if ny < y and y <= 11 and x >= 25:
            penalty += 15
        if nx < x and y == 11 and 22 < x <= 27:
            penalty += 25
        if y == 10 and x >= 24:
            if nx > x:
                penalty += 80
            elif nx < x:
                penalty -= 20
        if y == 11 and x >= 24:
            if nx > x:
                penalty += 40
            elif nx < x:
                penalty -= 8
    if to_corridor:
        if nx > x and y >= 11:
            penalty += 8
        if x == 24 and y == 11 and nx == 23:
            penalty += 50
        if x == 24 and y in (12, 13) and nx == 23:
            penalty += 50
        if ny > y and x == 24 and y in (11, 12, 13):
            penalty -= 6
    if nx > x:
        if y >= 15:
            penalty += 20
        elif y >= 14:
            penalty += 10
        elif y >= 11 and to_gate:
            penalty += 8
    return penalty


def session_walkable_for_map(state: dict | None, map_key: str) -> set[tuple[int, int]]:
    """Tiles confirmed walkable this session via successful navigation."""
    if not state:
        return set()
    raw = state.get("session_walkable", {}).get(map_key, [])
    return {tuple(tile) for tile in raw}


def record_session_walkable(
    state: dict,
    map_key: str,
    x: int,
    y: int,
) -> None:
    """Mark a tile walkable after a successful move."""
    session = dict(state.get("session_walkable", {}))
    tiles = list(session.get(map_key, []))
    key = (x, y)
    if key not in tiles:
        tiles.append(key)
    session[map_key] = tiles
    state["session_walkable"] = session


def session_blocked_for_map(state: dict | None, map_key: str) -> set[tuple[int, int]]:
    """Tiles confirmed blocked this session via failed navigation."""
    if not state:
        return set()
    raw = state.get("session_blocked", {}).get(map_key, [])
    return {tuple(tile) for tile in raw}


def record_session_blocked(
    state: dict,
    map_key: str,
    x: int,
    y: int,
) -> None:
    """Mark a tile blocked after a failed move into it."""
    session = dict(state.get("session_blocked", {}))
    tiles = list(session.get(map_key, []))
    key = (x, y)
    if key not in tiles:
        tiles.append(key)
    session[map_key] = tiles
    state["session_blocked"] = session


_DIRECTION_DELTA: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


def tile_blocked(
    map_key: str,
    x: int,
    y: int,
    *,
    state: dict | None = None,
) -> bool:
    """True when a tile is not walkable on the static grid or session overlay."""
    grid = MAP_GRIDS.get(map_key)
    session_walkable = session_walkable_for_map(state, map_key)
    session_blocked = session_blocked_for_map(state, map_key)
    return not _is_walkable(
        grid,
        x,
        y,
        session_walkable=session_walkable,
        session_blocked=session_blocked,
    )


def _is_perimeter_side_wall(
    map_key: str,
    x: int,
    y: int,
    direction: str,
) -> bool:
    """Side walls on map edge rows/cols are not interactable blocked-ahead."""
    grid = MAP_GRIDS.get(map_key)
    if not grid:
        return False
    height, width = len(grid), len(grid[0])
    if direction in ("left", "right") and (y == 0 or y == height - 1):
        return True
    if direction in ("up", "down") and (x == 0 or x == width - 1):
        return True
    return False


def map_edge_exit_direction(
    gs: GameState,
    *,
    heading_west: bool = False,
) -> str | None:
    """Cardinal to cross an outdoor map-edge warp on a warp-hint row."""
    hints = MAP_WARP_HINT_ROWS.get(gs.map_key, {})
    west_row = hints.get("west")
    if west_row is None or not heading_west or gs.player.y != west_row:
        return None
    edge = MAP_LANDMARK_ANCHORS.get(gs.map_key, {}).get("west_exit")
    if edge is None:
        return None
    edge_x, edge_y = edge
    pos = (gs.player.x, gs.player.y)
    if pos == (edge_x, edge_y):
        return "left"
    if pos == (edge_x + 1, edge_y):
        return "left"
    return None


def direction_blocked_ahead(
    map_key: str,
    x: int,
    y: int,
    direction: str,
    *,
    state: dict | None = None,
    require_in_bounds: bool = True,
) -> bool:
    """True when the tile one step in direction is blocked."""
    delta = _DIRECTION_DELTA.get(direction)
    if delta is None:
        return False
    dx, dy = delta
    nx, ny = x + dx, y + dy
    grid = MAP_GRIDS.get(map_key)
    if require_in_bounds and grid is not None and not _in_bounds(grid, nx, ny):
        return False
    return tile_blocked(map_key, nx, ny, state=state)


def approach_direction_toward_target(
    x: int,
    y: int,
    target: tuple[int, int],
) -> str | None:
    """Cardinal toward target; None when already standing on it."""
    toward = direction_toward(x, y, target[0], target[1])
    return None if toward == "a" else toward


def at_target_blocked_ahead_interact_eligible(
    map_key: str,
    x: int,
    y: int,
    target: tuple[int, int],
    *,
    state: dict | None = None,
    approach_from: tuple[int, int] | None = None,
) -> bool:
    """At nav target when the primary approach direction hits a blocked tile (indoor only)."""
    from src.graph.generic_interact import INDOOR_NAV_STUCK_MAPS

    if (x, y) != target:
        return False
    if map_key not in INDOOR_NAV_STUCK_MAPS:
        return False

    primary: str | None = None
    if approach_from is not None:
        primary = approach_direction_toward_target(
            approach_from[0], approach_from[1], target
        )
    if primary is None:
        for direction in _DIRECTION_DELTA:
            if _is_perimeter_side_wall(map_key, x, y, direction):
                continue
            if direction_blocked_ahead(
                map_key, x, y, direction, state=state, require_in_bounds=True
            ):
                primary = direction
                break
    if primary is None or _is_perimeter_side_wall(map_key, x, y, primary):
        return False
    return direction_blocked_ahead(
        map_key, x, y, primary, state=state, require_in_bounds=True
    )


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
    state: dict | None = None,
    _allow_backoff: bool = True,
) -> list[Direction]:
    """A* pathfinding on a collision grid. Returns list of directions."""
    if start_x == end_x and start_y == end_y:
        return []

    grid = MAP_GRIDS.get(map_key)
    session_walkable = session_walkable_for_map(state, map_key)
    session_blocked = session_blocked_for_map(state, map_key)
    if _allow_backoff:
        backoff = _east_row_session_backoff_prefix(
            start_x,
            start_y,
            end_x,
            end_y,
            map_key=map_key,
            grid=grid,
            session_blocked=session_blocked,
            state=state,
        )
        if backoff:
            bx, by = start_x, start_y
            for direction in backoff:
                dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[
                    direction
                ]
                bx, by = bx + dx, by + dy
            remainder = find_path(
                bx,
                by,
                end_x,
                end_y,
                map_key=map_key,
                max_steps=max(0, max_steps - len(backoff)),
                state=state,
                _allow_backoff=False,
            )
            return backoff + remainder

    goal = (end_x, end_y)
    open_set: list[tuple[int, int, int, int, list[Direction]]] = []
    heapq.heappush(open_set, (0, 0, start_x, start_y, []))
    visited: set[tuple[int, int]] = {(start_x, start_y)}

    while open_set:
        _, cost, x, y, path = heapq.heappop(open_set)
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
            if not _is_walkable(
                grid,
                nx,
                ny,
                goal=goal,
                session_walkable=session_walkable,
                session_blocked=session_blocked,
            ):
                continue
            new_path = path + [direction]  # type: ignore[list-item]
            if nx == end_x and ny == end_y:
                return new_path
            visited.add((nx, ny))
            step_cost = 1 + _warp_row_step_penalty(
                map_key,
                x,
                y,
                nx,
                ny,
                end_x=end_x,
                end_y=end_y,
                session_blocked=session_blocked,
            )
            h = abs(end_x - nx) + abs(end_y - ny)
            heapq.heappush(
                open_set, (cost + step_cost + h, cost + step_cost, nx, ny, new_path)
            )

    return _greedy_directions(
        start_x,
        start_y,
        end_x,
        end_y,
        grid,
        map_key=map_key,
        session_blocked=session_blocked,
    )


def _greedy_directions(
    x: int,
    y: int,
    tx: int,
    ty: int,
    grid: list[list[int]] | None,
    *,
    map_key: str = "",
    session_blocked: set[tuple[int, int]] | None = None,
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
        best: tuple[int, Direction] | None = None
        for d in candidates:
            ndx, ndy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
            nx, ny = cx + ndx, cy + ndy
            if not _is_walkable(
                grid, nx, ny, goal=goal, session_blocked=session_blocked
            ):
                continue
            penalty = _warp_row_step_penalty(
                map_key,
                cx,
                cy,
                nx,
                ny,
                end_x=tx,
                end_y=ty,
                session_blocked=session_blocked,
            )
            score = penalty
            if best is None or score < best[0]:
                best = (score, d)
        if best is not None:
            d = best[1]
            ndx, ndy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
            directions.append(d)
            cx, cy = cx + ndx, cy + ndy
            moved = True
        if not moved:
            break
    return directions


def direction_to_button(direction: Direction | str) -> str:
    return direction