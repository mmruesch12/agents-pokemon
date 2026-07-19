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
    "24:3": {"north": 5, "east": 8, "west": 7},
    # Route 30: north → R31/Mr.P; south y=53 → Cherrygrove (live x=6..7).
    # Route 30 north connection is on y=0 (west corridor x~4-7), not y=3.
    "26:1": {"north": 0, "south": 53},
    "26:3": {"north": 0},  # Cherrygrove City
    "26:2": {"west": 7},  # Route 31 → Violet gate at (4,6)/(4,7)
    "26:11": {"west": 5},  # R31 Violet Gate corridor y=4/5
    "10:5": {"north": 17},  # Violet City (gym approach row)
}

# Building/warp anchor tiles from MAP_GRIDS layout (bootstrap landmark seeding only).
MAP_LANDMARK_ANCHORS: dict[str, dict[str, tuple[int, int]]] = {
    "24:4": {
        "elms_lab_door": (6, 3),
        "west_exit": (0, 8),
    },
    "24:3": {
        # West corridor mid-point (ROM-reachable); final Cherrygrove edge is west_exit.
        "route_30_gate": (10, 8),
        "west_exit": (0, 7),
        # East toward New Bark (egg return / reverse of first crossing).
        "east_exit": (59, 8),
    },
    "26:1": {
        # Live ROM: Mr. Pokemon door warp is (17, 5) → map 26:10 (pret warp_event 17,5).
        "mr_pokemon_gate": (17, 5),
        # North map connection to Route 31 is on the west corridor (tiles ~4-7, y=0).
        # Live gym22 warped at (6,0); prefer x=6 to avoid soft-lock thrash at (4,4)/(4,5).
        "route_31_gate": (6, 0),
        # Alias for map-edge north (same tiles as route_31_gate).
        "north_exit": (6, 0),
        # South map edge into Cherrygrove (egg return / post-Mr.P southbound).
        # Live Silver: only x=6..7 connect y=48→53→Cherry; x=8..12 cliff at y=49.
        "south_exit": (7, 53),
    },
    "26:3": {
        "north_exit": (16, 0),  # ROM: Cherrygrove north warp → Route 30
        # Live Silver: east map edge into Route 29 (reverse of R29 west_exit).
        "east_exit": (39, 7),
    },
    "26:2": {
        # pret Route31.asm warp_event 4,6 / 4,7 → ROUTE_31_VIOLET_GATE.
        "west_gate": (4, 7),
    },
    "26:11": {
        # pret Route31VioletGate: east warps (9,4)/(9,5)↔R31; west (0,4)/(0,5)↔Violet.
        "east_exit": (9, 5),
        "west_exit": (0, 5),
    },
    "10:5": {
        # pret VIOLET_CITY gym warp is near SE of map; coarse open-grid seed.
        "gym_entrance": (18, 17),
        # East entry from R31 gate lands near (39, 25).
        "east_entry": (39, 25),
    },
    "24:5": {
        # Live Silver egg-return: (5,3) face-up + many A delivers egg (~50+ pages).
        # (4,2)/(4,3) may open other dialogs or fail on soft-locked approach.
        "desk_approach": (5, 3),
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
            "1101111000",  # (8,1)/(9,1) walkable after MeetMom (live Silver left from entry)
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
            # 60x18 — live Silver ROM BFS + west-corridor expansion (route29_gate_approach).
            # One-way ledge y=14→13 also enforced via ROUTE_29_Y14_CLIMB_X.
            "111111111111111111111111111111111111111111111111111111111111",  # y=0
            "111111111111111111111111111111111111111111111111111111111111",  # y=1
            "111111111111111100011111000000111111110000000000111111111111",  # y=2
            "111111111111111100000011010000111111110000000011111111111111",  # y=3
            "110000111111111100000001000000111100000000001111111111111111",  # y=4
            "110100011111111100011000000000011100000000001111111111111111",  # y=5
            # y6: close x9-16 false-opens that A* used as a west dead-end after
            # (16,4) down. Live westbound from mid/east uses (17,6) then y7 left
            # (validated ROM: (36,10)/(59,8) → west_exit). Keep x17 open as the
            # vertical drop from the y4 north bridge.
            # Note: (18–20,6) are live walls — do not false-open (bed_egg_to_gym6
            # right-from-17,6 failed). Egg-return walks (17,5) *without* A
            # (supervisor egg_return_no_a); tile itself is walkable.
            "000000001111111110111000000000000000001100111111100000111111",  # y=6
            "000000001000000000111110000000000000001100111110000100111111",  # y=7 west_exit
            "011100001000000111111110000001001111001100010000000000000000",  # y=8
            "011100001110111111111111111111111111001100010000000000000000",  # y=9
            "111100000000000011111111000010000000000000010000000000111111",  # y=10 gap x=28
            "111100000000000011111100000010000000000000010000000000111111",  # y=11
            # y12–13: open x16–17 for live egg-return (15,12)→(17,12)↓(17,14)
            # (manual + BFS bedroom_egg_r29). Was false wall L/R thrash x14–15.
            "111100000011100000111110000010000001110000010000001000111111",  # y=12
            "111100000011111000111100000011101111111111110000000000111111",  # y=13
            "111100001111110000000000000000000011110000000000111111111111",  # y=14
            "111100001111110000000000000000000011110000000000111111111111",  # y=15
            "111111111111111111111111000100000000000000001111111111111111",  # y=16
            "111111111111111111111111110000000000000000001111111111111111",  # y=17
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
    # Coarse open grids for corridor maps (session overlays refine walkability).
    "26:3": _grid_from_rows(
        [
            # Live ROM BFS from cherrygrove_entry (Silver); north exit (16,0)/(17,0).
            "1111111111111111001111111111111111111111",  # y=0
            "1111111111111111001111111111111111111111",  # y=1
            "1111111111111111001111111111111111111111",  # y=2
            "1111111111111111001111111111111111111111",  # y=3
            "1111111111110000000000000000000011111111",  # y=4
            "1111111111110000000000000000000011111111",  # y=5
            # y=6–7: east corridor x=33–39 open to Route 29 (live Silver).
            # Rival coord_events at (33,6)/(33,7) — A* to east_exit must step on these
            # (do not force a y=9-only detour that skips SCENE_CHERRYGROVECITY_MEET_RIVAL).
            "1111111111000000111100000000000000000000",  # y=6 east bridge open
            "1111111111000000111100100000000000000000",  # y=7
            "1111111111000000000000001111001000111111",  # y=8
            "1111111111000000000000011111000000111111",  # y=9
            "1111111111111100000000000000001111111111",  # y=10
            "1111111111111100000000000000001111111111",  # y=11
            "1111111111111111111111000000000000111111",  # y=12
            "1111111111111111111111000000000000111111",  # y=13
            "1111111111111111111111111111111111111111",  # y=14
            "1111111111111111111111111111111111111111",  # y=15
            "1111111111111111111111111111111111111111",  # y=16
            "1111111111111111111111111111111111111111",  # y=17
        ]
    ),
    # Route 31 (40×18): live Silver BFS from east entry (post-egg thrash).
    # Open-grid pure-left false-paths through trees (x≈21–23 wall at y=11–15).
    # Gate warps at (4,6)/(4,7) left → 26:11; south y=17 warps → R30.
    # Live BFS from bed_chain_r31 (30,14) → gate (4,7) (2026-07-17):
    #   y9 west to (16,9) → down (16,10–12) → west on y12 (x16→x9) → north to
    #   y8 west strip → (4,7). Never enters Wade LOS (18,12–15; trainer at 18,15
    #   facing up, sight 3). y8 x13 is a live wall — keep blocked so A* does not
    #   false-left at (14,8). Open (16,11) so the live vertical corridor exists.
    "26:2": _grid_from_rows(
        [
            "1111111111111111111111111111111111111111",  # y0
            "1111111111111111111111111111111111111111",  # y1
            "1111111111111111111111111111111111111111",  # y2
            "1111111111111111111111111111111111111111",  # y3
            "1111110000000111111111111111000011111111",  # y4
            "1111110100000100111111111111010111111111",  # y5
            "1111000000000100000011111111000000000011",  # y6
            "1111000000000100110011111111000000000011",  # y7 gate (4,7)
            "1111110000000100000000000000000000000111",  # y8 x13 wall (live solid)
            "1111111110111100000000000000000000000111",  # y9
            "1111110000000011000000111111111100000111",  # y10 open x16
            # y11: open x16 (live BFS vertical (16,10)↔(16,12)); block Wade x18
            "1111110000000011011011110011111100001111",  # y11
            # y12–15: block Wade column x18 (trainer 18,15 facing north)
            "1111111100000000001000110001111100001111",  # y12 open x12–17 west of Wade
            "1111111100000000001001110001111110001111",  # y13 + (32,13) A-spam
            # y14: live walk (27,14)→(28,14)→(29,14) (probe bed_chain_r30_y13).
            # Keeping (28,14) blocked forced A* onto (28,15) which hard-freezes
            # SCRIPT_READ textbox that pure A never clears (live gym47/48 probe).
            "1111111111000000001001110000000000111111",  # y14 open x24–33 incl (28,14)
            "1111111111000000001001110000000000111111",  # y15 Wade (18,15)
            "1111111111111111111111110000111111111111",  # y16
            "1111111111111111111111110000111111111111",  # y17 R30 edge
        ]
    ),
    # Route 30: 0=walkable. Live Silver BFS (egg-return + climb seeds):
    # - East pocket false-opens (e.g. (9,8)) caused pure-down thrash after Mr.P.
    # - Mid/east walkability from live BFS; west x0-5 + y0-5 union preserves R31.
    # - South climb north only at x=12 from y=48 (ROUTE_30_Y48_NORTH_X).
    # - y48-49 open x6-13; y50-53 south to Cherry only x6-7.
    # - Soft-lock SCRIPT_READ is from A-spam on signs/NPCs, not the tile itself
    #   (live BFS walks (12,14)/(10,19) fine without A). Prefer geometry fixes.
    # - East mid (x≥10, y≤17) cannot cross west until ~y24 (live BFS); y18–23
    #   must not false-join or A* detours into thrash then A-spam soft-lock.
    # - Live (12,12) left is solid wall — keep x11 blocked on y11–13.
    # - Live west join path: (12,12)↓(12,16)←(10,17)↓(10,23)→(14,23)↓(15,30)←(5,30).
    "26:1": _grid_from_rows(
        [
            # Live BFS (bed_chain_r30_y13 → R31): north edge only (6,0) walkable of
            # west strip; path is x1 climb → (2,7)→(5,5)→(5,4)/(6,4)→(6,0).
            # y0–4 false-opens caused pure-up thrash then (4,4) SCRIPT_READ pin.
            "11111101111111111111",  # y0  live only (6,0) R31 warp
            "11111000111111111111",  # y1  live x5-7
            "11110000111111111111",  # y2  live x4-7
            "11111100111100001111",  # y3  live x6-7; east pocket x12-15
            # y4: live x4-7 but (4,4) soft-lock A-pin — keep blocked; use x5-7.
            "11111000110000001111",  # y4  x0-4 blocked; approach via x5–7
            "11000000110100010011",  # y5  Mr P door (17,5); mid barrier; live x2-7
            "00000000100000000000",  # y6  live: no false-open at x9 south
            # y7: live BFS walks (2,7); keep (4,7) blocked (not in live set).
            # Soft-lock was A-spam residue, not the tile (open (2,7) for R31 path).
            "00001000100000000000",  # y7  (2,7) open live; (4,7) blocked; (9,7) thrash
            "00000001110000000000",  # y8  (9,8) solid live — force east then south
            # y9–10: wall x6–7 only (post-rival (8,10) + east pocket stay open).
            # y11–17: wall x6–11 so live (12,12) cannot false-left; east is x12+.
            # Live BFS: pure-up at x2–5 into y11 fails — only (0,11)/(1,11).
            "00000011000000000000",  # y9
            "00000011000000000011",  # y10 post-rival (8,10)
            "00111111111100000011",  # y11 live only x0-1 (x2-5 false-open pure-up)
            "00000011111100000011",  # y12 live left from (12,12) fails
            "00100011111100000011",  # y13 live (2,13) solid; x0-1,3-5 open
            "00000011111100000000",  # y14 live BFS uses (12,14) south
            "00000011111100000000",  # y15
            "00000011111100000000",  # y16
            "00000000110000000000",  # y17 live (10,17) east corridor
            # y18-23: east corridor x10–15; barrier x8-9 until y24 full join.
            "00000000110000000000",  # y18
            "00000000110000000000",  # y19 live (10,19)
            "00000000110000000000",  # y20
            "00000000110000000000",  # y21
            "00000000110000000000",  # y22
            "00000000110000000000",  # y23 live (10,23)/(12,23)/(14,23)
            "00000000000000001111",  # y24 live west↔east join
            "00000010000000001111",  # y25
            "00000000000011001111",  # y26
            "00000000000011001111",  # y27
            "11000000001100001111",  # y28
            "11000000001101001111",  # y29
            "11000000000000000011",  # y30
            "11000000000000000011",  # y31
            "11000000000000000011",  # y32
            "11000000000000000011",  # y33
            "11001111000000001111",  # y34
            "11001111000000001111",  # y35
            "11001111111100001111",  # y36
            "11111111111100001111",  # y37
            "11000011111100111111",  # y38
            "11000111111100111111",  # y39 berry house (7,39)
            "11000000000000111111",  # y40
            "11000000000000111111",  # y41
            "11111100000000111111",  # y42
            "11111100010000111111",  # y43
            "11111100000000111111",  # y44
            "11111100000000111111",  # y45
            "11111100000000111111",  # y46
            "11111111111100111111",  # y47
            # y48-49: open x6-13 (north climb only x=12). y50-53: x6-7 only.
            "11111100000000111111",  # y48
            "11111100000000111111",  # y49
            "11111100111111111111",  # y50
            "11111100111111111111",  # y51
            "11111100111111111111",  # y52
            "11111100111111111111",  # y53 south to Cherry
        ]
    ),
    "26:11": _grid_from_rows(  # Route 31 Violet Gate (10x9; pret warps y=4/5)
        [
            "1111111111",  # y0
            "1111111111",  # y1
            "1000000001",  # y2
            "1000000001",  # y3
            "0000000000",  # y4 west↔Violet, east↔R31
            "0000000000",  # y5
            "1111111111",  # y6
            "1111111111",  # y7
            "1111111111",  # y8
        ]
    ),
    # Violet City: 20×18 blocks → 40×36 tiles.
    # Live bed_chain_gym43 / r31_gym: pure-left on y=17 from x=22 fails (wall at
    # x=21); door is entered from (18,18)↑(18,17). A* must route y=18 west then
    # up, not north thrash at x=22 (false-open (21,y) for y≤17).
    # Also block non-gym warps + east false-up walls (up from y=24 at x≥28 fails).
    "10:5": _grid_from_rows(
        [
            "".join(
                "1"
                if (x, y)
                in {
                    (9, 17),  # mart
                    (30, 17),  # academy
                    (3, 15),  # nickname house
                    (31, 25),  # pokecenter
                    (21, 29),  # kyle house
                    (23, 5),  # sprout tower
                    (39, 24),  # gate (stay on y=25 corridor)
                    # Gym building: east wall x=21 (y≤17) + south face except door.
                    # Door tile (18,17) stays open (warp into 10:7).
                    *{(21, yy) for yy in range(18)},
                    (19, 17),
                    (20, 17),
                    # East approach: live up from (x,24) x=28–38 hits solid y=23.
                    *{(xx, 23) for xx in range(28, 39)},
                }
                else "0"
                for x in range(40)
            )
            for y in range(36)
        ]
    ),
    "10:7": _grid_from_rows(  # Violet Gym interior (5x8 blocks)
        [
            "1111111111",
            "1000000001",
            "1000000001",
            "1000000001",
            "1000000001",
            "1000000001",
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
    # Route 30 northbound to R31 gate (6,0): live BFS climbs x0–1 at y12–7 then
    # east via (2,7)→(6,0). Grid already blocks y11 x2–5; bias A* onto x0–1
    # while still south of y8; prefer x2–7 only on the north approach ledge.
    if map_key == "26:1" and end_y == 0 and end_x <= 7 and end_y < y:
        if y >= 8 and 0 <= nx <= 1 and ny <= y:
            penalty -= 4
        if y <= 7 and 2 <= nx <= 7 and ny <= y:
            penalty -= 2
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
    to_west_approach = 10 <= end_y <= 12 and end_x <= 12
    to_corridor = end_y >= 14
    to_west_descent = (end_x, end_y) == (25, 11)
    if not to_gate and not to_corridor and not to_west_descent and not to_west_approach:
        return 0
    penalty = 0
    if to_gate or to_west_approach:
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
        if y == 10 and x == 27 and ny < y:
            penalty += 100
        if y == 10 and x == 27 and ny > y:
            penalty -= 12
        if y == 11 and x <= 27 and ny > y:
            penalty += 40
        if y == 11 and x <= 24 and ny > y and end_y >= 10:
            penalty += 100
        if y == 11 and x <= 24 and nx < x and end_y >= 10:
            penalty -= 12
        if y == 12 and x > end_x and nx < x:
            penalty -= 15
        if y == 12 and x > end_x and ny > y:
            penalty += 50
        if y == 10 and x == 44:
            if ny > y:
                penalty -= 20
            elif ny < y or nx != x:
                penalty += 80
    if to_west_descent:
        if y == 10 and x == 27 and nx < x:
            penalty += 80
        if y == 10 and x == 27 and ny > y:
            penalty -= 15
    if to_corridor:
        if nx > x and y >= 11:
            penalty += 8
        if x == 24 and y == 11 and nx == 23:
            penalty += 50
        if x == 24 and y in (12, 13) and nx == 23:
            penalty += 50
        if ny > y and x == 24 and y in (11, 12, 13):
            penalty -= 6
    # On the south ledge row, the only west-bound escape is east to a climb gap
    # (x in ROUTE_29_Y14_CLIMB_X) then north — do not punish east progress there.
    if nx > x:
        if y >= 15 and x >= 32:
            penalty += 20
        elif y >= 14 and x >= 32:
            penalty += 10
        elif y >= 11 and y < 14 and (to_gate or to_west_approach):
            penalty += 8
    if nx < x and y >= 15 and x < 22 and (to_gate or to_west_approach):
        # West into the sign pocket while still below the climb is a dead-end trap.
        penalty += 40
    if y == 14 and ny == 13 and nx in ROUTE_29_Y14_CLIMB_X and (to_gate or to_west_approach):
        penalty -= 12
    if y == 14 and nx > x and x < 31 and (to_gate or to_west_approach):
        penalty -= 6
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

# Route 29 south-facing ledge (y=13→14 down OK; y=14→13 up only at climb gaps).
# Mid gaps 22–27,31: live westbound climb. East gaps 44–47: required for egg-return
# eastbound (westbound A* reverse needs those climbs; without them max-x≈47).
# Low gaps 4–7: also dual-walkable on the static grid.
ROUTE_29_Y14_CLIMB_X: frozenset[int] = frozenset(
    {4, 5, 6, 7, 22, 23, 24, 25, 26, 27, 31, 44, 45, 46, 47}
)

# Route 30 south approach: from y=48 only x=12 climbs north (live ROM probe).
ROUTE_30_Y48_NORTH_X: frozenset[int] = frozenset({12})


def _directional_step_allowed(
    map_key: str,
    x: int,
    y: int,
    nx: int,
    ny: int,
) -> bool:
    """False for one-way ledge climbs that static grids cannot express."""
    if map_key == "24:3":
        if y == 14 and ny == 13 and nx == x and x not in ROUTE_29_Y14_CLIMB_X:
            return False
        return True
    if map_key == "26:1":
        if y == 48 and ny == 47 and nx == x and x not in ROUTE_30_Y48_NORTH_X:
            return False
        return True
    return True


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
    heading_east: bool = False,
    heading_south: bool = False,
    heading_north: bool = False,
) -> str | None:
    """Cardinal to cross an outdoor map-edge warp on a warp-hint row.

    Edge presses are gated on explicit heading flags so entry tiles (e.g. R29
    east_exit while westbound, R30 south_exit while northbound) do not bounce
    the agent back through the warp they just used.
    """
    hints = MAP_WARP_HINT_ROWS.get(gs.map_key, {})
    anchors = MAP_LANDMARK_ANCHORS.get(gs.map_key, {})
    pos = (gs.player.x, gs.player.y)
    # West map-edge (Route 29 → Cherrygrove, Route 31 → Violet, …).
    west_row = hints.get("west")
    if west_row is not None and heading_west and gs.player.y == west_row:
        edge = anchors.get("west_exit") or anchors.get("west_gate")
        if edge is not None:
            edge_x, edge_y = edge
            if pos in {(edge_x, edge_y), (edge_x + 1, edge_y)}:
                return "left"
    # North map-edge (Cherrygrove → Route 30). Standing on north_exit needs "up".
    north_row = hints.get("north")
    north_exit = anchors.get("north_exit")
    if (
        heading_north
        and north_row is not None
        and north_exit is not None
        and gs.player.y == north_row
        and pos[0] in {north_exit[0], north_exit[0] - 1, north_exit[0] + 1}
    ):
        if pos == north_exit or abs(pos[0] - north_exit[0]) <= 1:
            return "up"
    # South map-edge (Route 30 → Cherrygrove). Live warp at x=6..7, y=53.
    south_row = hints.get("south")
    south_exit = anchors.get("south_exit")
    if heading_south and south_row is not None and gs.player.y == south_row:
        if south_exit is not None and abs(pos[0] - south_exit[0]) <= 1:
            return "down"
        if south_exit is None and 6 <= gs.player.x <= 7:
            return "down"
    # East map-edge only when explicitly heading east (egg-return).
    east_exit = anchors.get("east_exit")
    if (
        heading_east
        and east_exit is not None
        and gs.player.x == east_exit[0]
        and abs(gs.player.y - east_exit[1]) <= 1
    ):
        return "right"
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


# pret wPlayerStruct direction: 0 down, 4 up, 8 left, 12 right.
_FACING_TO_DIRECTION: dict[int, str] = {0: "down", 4: "up", 8: "left", 12: "right"}
_DIRECTION_TO_FACING: dict[str, int] = {v: k for k, v in _FACING_TO_DIRECTION.items()}


def facing_to_direction(facing: int) -> str | None:
    return _FACING_TO_DIRECTION.get(int(facing))


def interact_face_direction(
    map_key: str,
    x: int,
    y: int,
    target: tuple[int, int],
    *,
    state: dict | None = None,
    approach_from: tuple[int, int] | None = None,
) -> str | None:
    """Cardinal the player must face to interact with the blocked-ahead object."""
    from src.graph.generic_interact import INDOOR_NAV_STUCK_MAPS

    if (x, y) != target or map_key not in INDOOR_NAV_STUCK_MAPS:
        return None
    primary: str | None = None
    if approach_from is not None:
        primary = approach_direction_toward_target(
            approach_from[0], approach_from[1], target
        )
    if primary is None:
        for direction in ("up", "down", "left", "right"):
            if _is_perimeter_side_wall(map_key, x, y, direction):
                continue
            if direction_blocked_ahead(
                map_key, x, y, direction, state=state, require_in_bounds=True
            ):
                primary = direction
                break
    if primary is None or _is_perimeter_side_wall(map_key, x, y, primary):
        return None
    if not direction_blocked_ahead(
        map_key, x, y, primary, state=state, require_in_bounds=True
    ):
        return None
    return primary


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
    return (
        interact_face_direction(
            map_key,
            x,
            y,
            target,
            state=state,
            approach_from=approach_from,
        )
        is not None
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
    max_steps: int = 80,
    state: dict | None = None,
    _allow_backoff: bool = True,
) -> list[Direction]:
    """A* pathfinding on a collision grid. Returns list of directions."""
    if start_x == end_x and start_y == end_y:
        return []

    grid = MAP_GRIDS.get(map_key)
    session_walkable = session_walkable_for_map(state, map_key)
    session_blocked = session_blocked_for_map(state, map_key)
    # Route 29 west exit needs ~100 steps from east entry (y14 climb + north bridge).
    if map_key == "24:3" and max_steps < 120:
        max_steps = 120
    # Route 31 west to Violet gate detours around tree walls (~50 steps).
    if map_key == "26:2" and max_steps < 100:
        max_steps = 100
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
            # Only accept backoff if remainder actually reaches the goal (or is empty
            # because backoff already landed on the goal). Incomplete A* prefixes
            # thrash (Route 29 gate left/left without a west path).
            if (bx, by) == (end_x, end_y):
                return backoff
            if remainder:
                rx, ry = bx, by
                for direction in remainder:
                    dx, dy = {
                        "up": (0, -1),
                        "down": (0, 1),
                        "left": (-1, 0),
                        "right": (1, 0),
                    }[direction]
                    rx, ry = rx + dx, ry + dy
                if (rx, ry) == (end_x, end_y):
                    return backoff + remainder
            # Fall through to full A* without the broken prefix.

    goal = (end_x, end_y)
    open_set: list[tuple[int, int, int, int, list[Direction]]] = []
    heapq.heappush(open_set, (0, 0, start_x, start_y, []))
    visited: set[tuple[int, int]] = {(start_x, start_y)}

    while open_set:
        _, cost, x, y, path = heapq.heappop(open_set)
        # Do not return incomplete paths when the step budget is hit — that caused
        # Route 29 gate thrash (A* handed left/left without reaching west gap).
        if len(path) >= max_steps:
            continue

        for direction, dx, dy in [
            ("up", 0, -1),
            ("down", 0, 1),
            ("left", -1, 0),
            ("right", 1, 0),
        ]:
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited:
                continue
            if not _directional_step_allowed(map_key, x, y, nx, ny):
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
    # Incomplete greedy prefixes thrash (e.g. gate left/left without a west path).
    if (cx, cy) != (tx, ty):
        return []
    return directions


def direction_to_button(direction: Direction | str) -> str:
    return direction