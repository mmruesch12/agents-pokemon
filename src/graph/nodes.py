"""Multi-agent graph nodes: Supervisor, Planner, Navigator, Battler, Critic, Memory."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.emulator.bootstrap import needs_bootstrap, pick_bootstrap_button
from src.graph.generic_interact import (
    INDOOR_NAV_STUCK_MAPS,
    INTERACT_NO_PROGRESS_RECOVERY,
    arm_interact_stall_escape,
    clear_interact_stall_escape,
    clear_pocket_stuck,
    generic_force_interactor,
    generic_is_interact_needed,
    generic_prefer_interact_candidate,
    generic_stuck_interact_fallback,
    interact_stall_recovery_active,
    outdoor_interact_recovery_active,
    in_navigation_pocket,
    record_pocket_nav_failure,
    should_arm_interact_stall,
)
from src.graph.navigation_resolve import resolve_navigation_target
from src.graph.nav_thrash import append_nav_position, nav_thrash_severity
from src.graph.llm import llm_battle, llm_navigate, llm_plan
from src.graph.pathfinding import (
    MAP_GRIDS,
    MAP_LANDMARK_ANCHORS,
    MAP_WARP_HINT_ROWS,
    _is_walkable,
    at_target_blocked_ahead_interact_eligible,
    facing_to_direction,
    interact_face_direction,
    direction_toward,
    find_path,
    record_session_blocked,
    record_session_walkable,
    session_blocked_for_map,
    session_walkable_for_map,
)
from src.graph.phases import early_progression, house_exit, starter_quest
from src.graph.state import AgentState, update_game_state
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_INTERIOR_ID,
    MR_POKEMONS_HOUSE_ENTRANCE_ID,
    apply_landmark_discovery,
    discover_elms_lab_landmarks,
    discover_map_visit_landmark,
    discover_mr_pokemon_entrance_landmark,
    discover_quest_transition_landmarks,
    find_landmark,
    format_landmarks_for_prompt,
    landmark_coords,
    landmark_known,
    memory_data_dir,
    parse_position_key,
    retrieve_landmarks_from_state,
)
from src.memory.long_term_memory import LongTermMemory
from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
    MAP_KEY_ROUTE_31,
    MAP_KEY_VIOLET_CITY,
    MAP_KEY_VIOLET_GYM,
    PLAYERS_HOUSE_1F_DOOR,
)
from src.state.models import GameState
from src.state.script_constants import (
    SCRIPT_FLAG_SCRIPT_RUNNING,
    SCRIPT_READ,
    SCRIPT_WAIT,
    SCRIPT_WAIT_MOVEMENT,
)

logger = logging.getLogger(__name__)

STUCK_THRESHOLD = int(os.getenv("STUCK_THRESHOLD", "10"))
STUCK_ARBITRATION_THRESHOLD = int(os.getenv("STUCK_ARBITRATION_THRESHOLD", "2"))
NAVIGATION_REPEAT_THRESHOLD = int(os.getenv("NAVIGATION_REPEAT_THRESHOLD", "3"))
INTERACT_HOLD_FRAMES = int(os.getenv("INTERACT_HOLD_FRAMES", "30"))
OUTDOOR_INTERACT_TICKS = int(os.getenv("OUTDOOR_INTERACT_TICKS", "120"))
SCRIPT_WAIT_TICKS = int(os.getenv("SCRIPT_WAIT_TICKS", "45"))
ROUTE_29_Y11_DEAD_END: tuple[int, int] = (22, 11)
ROUTE_29_FORCED_LEDGE_STEP: dict[tuple[int, int], str] = {
    # East ledge pocket: only south detour reaches the west corridor; up/down
    # thrash between y=8–9 never increases stuck_count (position always changes).
    (44, 8): "down",
    (44, 9): "down",
    (44, 10): "down",
    (44, 11): "down",
    (44, 12): "down",
    (44, 13): "down",
    (45, 8): "down",
    (45, 9): "down",
    (45, 10): "down",
    (45, 11): "down",
    (45, 12): "down",
    (45, 13): "down",
    # East wall on y=13: never force left into solid (live thrash at 44,13).
    (43, 13): "down",
    (42, 13): "down",
    # y=14 solid #### at x=34-37: tiles immediately east of the wall (left solid).
    # Live Silver also parks NPC/sign contacts along x≈39–44 on y=14; left thrash
    # never moves (live west_entrance stuck at 44,14 then 40,14). Drop south first
    # so A* can skirt the wall on y=15–16 toward the west gap.
    (38, 14): "down",
    (39, 14): "down",
    (40, 14): "down",
    (41, 14): "down",
    (42, 14): "down",
    (43, 14): "down",
    (44, 14): "down",
    (45, 14): "down",
    (46, 14): "down",
    (47, 14): "down",
    # y=15 at wall edge: left is solid (#### x=34-37); drop to open y=16 then west.
    (38, 15): "down",
    (39, 15): "left",
    (40, 15): "left",
    (41, 15): "left",
    (42, 15): "left",
    (43, 15): "left",
    (44, 15): "left",
    (45, 15): "left",
    (46, 15): "left",
    (47, 15): "left",
    # Open south strip under the wall — commit west toward climb gaps.
    (33, 16): "left",
    (34, 16): "left",
    (35, 16): "left",
    (36, 16): "left",
    (37, 16): "left",
    (38, 16): "left",
    (39, 16): "left",
    (40, 16): "left",
    (25, 11): "down",
    (26, 11): "down",
    (27, 11): "down",
    # y=14→13 climb gaps (ROUTE_29_Y14_CLIMB_X): never thrash down back to y=14.
    (22, 14): "up",
    (23, 14): "up",
    (24, 14): "up",
    (25, 14): "up",
    (26, 14): "up",
    (27, 14): "up",
    (31, 14): "up",
    # After y=14 climb: A* to west/gate starts with "down" then east on y=14–16.
    # Forcing "right" on y=13 caused live left↔right thrash (26,13↔27,13) with
    # stuck_count=0 (position always changes) while west_row also flipped left.
    (22, 13): "down",
    (23, 13): "down",
    (24, 13): "down",
    (25, 13): "down",
    (26, 13): "down",
    (27, 13): "down",
    (28, 13): "down",
}
# When west of this column on Route 29, east-ledge forced downs no longer apply.
ROUTE_29_EAST_LEDGE_FORCE_MIN_X = 40
ROUTE_29_SIGN_TRAP_ROWS = (14, 15)
ROUTE_29_SIGN_TRAP_MAX_X = 14
ROUTE_29_SIGN_TRAP_Y15_EAST_MAX_X = 17
ROUTE_29_Y15_EAST_DEAD_END_X = 33


def _route_29_sign_dead_end_path_step(
    gs: GameState,
    path: list[str],
    target: tuple[int, int],
) -> str | None:
    """Only correct path steps that walk into the ROM-blocked sign wall.

    A* already escapes the y=14–15 pocket via up/right then the west corridor.
    Prior overrides that forced east/down against a valid escape created a pure-nav
    loop (stuck_count stayed 0). Intervene only when path[0] is into solid tiles
    or the far y=15 east cul-de-sac.
    """
    from src.graph.navigation_resolve import ROUTE_29_WEST_GATE_APPROACH

    if gs.map_key != MAP_KEY_ROUTE_29 or not path:
        return None
    px, py = gs.player.x, gs.player.y
    if py not in ROUTE_29_SIGN_TRAP_ROWS:
        return None
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    west_approach = ROUTE_29_WEST_GATE_APPROACH
    step = path[0]
    # West wall of sign pocket: x<=14 cannot go left on y=14–15.
    if step == "left" and px <= ROUTE_29_SIGN_TRAP_MAX_X:
        # Prefer A* rest if present; otherwise step east to open space.
        for alt in path[1:4]:
            if alt != "left":
                return alt
        return "right"
    # Far east cul-de-sac on y=15: do not keep walking right into the dead end.
    if (
        gate
        and py == 15
        and px >= ROUTE_29_Y15_EAST_DEAD_END_X
        and target in (gate, west_approach)
        and step == "right"
    ):
        return "up"
    return None


def _route_29_y16_corridor_path_step(
    gs: GameState,
    path: list[str],
    target: tuple[int, int],
) -> str | None:
    """ROM y=16 west dead-end: left is blocked at x=24 when heading east, not toward gate."""
    from src.graph.navigation_resolve import (
        ROUTE_29_WEST_GATE_APPROACH,
        ROUTE_29_Y16_EAST_ANCHOR,
    )
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    if gs.map_key != MAP_KEY_ROUTE_29 or not path:
        return None
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    west_approach = ROUTE_29_WEST_GATE_APPROACH
    if gate and target in (gate, west_approach):
        return None
    px, py = gs.player.x, gs.player.y
    anchor = ROUTE_29_Y16_EAST_ANCHOR
    if (px, py) == anchor and path[0] in ("left", "up"):
        return "right"
    if (px, py) == (anchor[0], anchor[1] - 1) and path[0] in ("up", "down"):
        return "right"
    return None


def _route_29_west_row_path_step(
    gs: GameState,
    target: tuple[int, int],
    path: list[str],
) -> str | None:
    """Post-climb y=13: prefer A* "down" toward the open south strip (not L/R thrash)."""
    from src.graph.navigation_resolve import ROUTE_29_WEST_GATE_APPROACH

    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    west_approach = ROUTE_29_WEST_GATE_APPROACH
    west_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit")
    if (
        gs.map_key != MAP_KEY_ROUTE_29
        or not path
        or gate is None
    ):
        return None
    if target not in (gate, west_approach, west_exit, (4, 10)):
        return None
    px, py = gs.player.x, gs.player.y
    # y=13 strip after climb: never force left against A* down (live 26↔27 thrash).
    if py == 13 and 22 <= px <= 32 and path[0] == "down":
        return "down"
    if py == 13 and px == 22 and path[0] in ("right", "left"):
        return "down"
    return None


def _route_29_south_corridor_path_step(
    gs: GameState,
    target: tuple[int, int],
    path: list[str],
) -> str | None:
    """ROM-valid progress on the south corridor toward re-entry or the Route 30 gate."""
    from src.graph.navigation_resolve import (
        ROUTE_29_CORRIDOR_EAST_REENTRY,
        ROUTE_29_WEST_GATE_APPROACH,
    )

    reentry = ROUTE_29_CORRIDOR_EAST_REENTRY
    if gs.map_key != MAP_KEY_ROUTE_29 or not path:
        return None
    px, py = gs.player.x, gs.player.y
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    west_approach = ROUTE_29_WEST_GATE_APPROACH
    if (
        py == reentry[1]
        and target[0] >= reentry[0]
        and px < reentry[0]
        and path[0] == "right"
    ):
        return "right"
    if py == reentry[1] and px == reentry[0] - 1 and path[0] == "right":
        return "left"
    if (
        gate
        and target in (gate, west_approach)
        and py >= reentry[1]
        and px <= reentry[0] + 1
    ):
        return path[0]
    return None


def _route_29_ledge_path_step(
    gs: GameState,
    target: tuple[int, int],
    path: list[str],
) -> str | None:
    """Follow A* strictly on the east ledge row toward the connector or gate."""
    from src.graph.navigation_resolve import (
        ROUTE_29_EAST_LEDGE_DEAD_END_X,
        ROUTE_29_SOUTH_CORRIDOR,
        ROUTE_29_WEST_GATE_APPROACH,
    )

    forced = ROUTE_29_FORCED_LEDGE_STEP.get((gs.player.x, gs.player.y))
    if forced is not None:
        # Match select_navigation_action: climb-up yields to A* left/right.
        if not (
            forced == "up"
            and path
            and path[0] in ("left", "right")
        ):
            return forced
    west_approach = ROUTE_29_WEST_GATE_APPROACH
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    west_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit")
    # East pocket (x≥40, y≤11): always prefer A* first step when heading west/south
    # corridor — never LLM "up" thrash while stuck_count stays 0.
    if (
        gs.map_key == MAP_KEY_ROUTE_29
        and path
        and gs.player.x >= ROUTE_29_EAST_LEDGE_FORCE_MIN_X
        and gs.player.y <= 11
        and (
            target == ROUTE_29_SOUTH_CORRIDOR
            or (gate is not None and target == gate)
            or (west_exit is not None and target == west_exit)
            or (west_approach is not None and target == west_approach)
            or target[0] < gs.player.x
            or target[1] > gs.player.y
        )
    ):
        if path[0] != "up":
            return path[0]
        # Path should not climb north out of the pocket toward Cherrygrove.
        for step in path[1:4]:
            if step != "up":
                return step
        return "down"
    if (
        gs.map_key == MAP_KEY_ROUTE_29
        and gs.player.y == west_approach[1]
        and gs.player.x > west_approach[0]
        and path
        and (
            target == west_approach
            or (gate and target == gate)
            or (west_exit and target == west_exit)
        )
    ):
        return path[0]
    ledge = (27, 10)
    west_descent = (25, 11)
    if (
        gate
        and target in (gate, ledge, west_descent, ROUTE_29_SOUTH_CORRIDOR)
        and gs.map_key == MAP_KEY_ROUTE_29
        and gs.player.y <= 11
        and gs.player.x >= 24
        and path
    ):
        return path[0]
    if (
        west_exit
        and target == west_exit
        and gs.map_key == MAP_KEY_ROUTE_29
        and gs.player.x >= ROUTE_29_EAST_LEDGE_DEAD_END_X
        and path
    ):
        return path[0]
    return None


def _interact_tick_frames(gs: GameState) -> int:
    """Outdoor multi-page signs need long ticks even between text-box pages."""
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return SCRIPT_WAIT_TICKS
    meta = gs.raw_metadata or {}
    if (
        gs.in_text_box
        or meta.get("in_script")
        or meta.get("script_active")
        or meta.get("script_mode") == SCRIPT_READ
    ):
        # Route trainers / multi-page outdoor scripts need longer settle time.
        return max(OUTDOOR_INTERACT_TICKS, 120)
    return SCRIPT_WAIT_TICKS

_DIRECTION_DELTA = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
_OPPOSITE_DIRECTIONS = frozenset({("left", "right"), ("right", "left"), ("up", "down"), ("down", "up")})

def _long_term_memory() -> LongTermMemory:
    return LongTermMemory(data_dir=memory_data_dir())


def score_visit_aware_candidate(
    direction: str,
    gs: GameState,
    state: AgentState,
) -> float:
    """Prefer unvisited adjacent tiles; penalize immediate backtrack oscillation."""
    if direction == "a":
        return 0.0
    dx, dy = _DIRECTION_DELTA.get(direction, (0, 0))
    nx, ny = gs.player.x + dx, gs.player.y + dy
    pos_key = f"{gs.map_key}:{nx}:{ny}"
    visited = set(state.get("visited_positions", []))
    score = 2.0 if pos_key not in visited else -1.0
    nav_history = [
        entry.split(":")[1].split("@")[0]
        for entry in state.get("short_term_history", [])
        if entry.startswith("navigate:")
    ]
    if len(nav_history) >= 2:
        last_dir = nav_history[-1]
        prev_dir = nav_history[-2]
        if (prev_dir, direction) in _OPPOSITE_DIRECTIONS or (last_dir, direction) in _OPPOSITE_DIRECTIONS:
            score -= 1.5
    return score


def _parse_history_entry(item: str) -> tuple[str, str, str | None] | None:
    """Return (kind, payload, position) for navigate:/interact: history entries."""
    if "@" not in item or ":" not in item:
        return None
    action, pos = item.split("@", 1)
    kind, payload = action.split(":", 1)
    return kind, payload, pos


def repeating_nav_direction(history: list[str], *, min_count: int | None = None) -> str | None:
    """Direction repeated at the same tile (e.g. teacher gate blocking east)."""
    min_count = NAVIGATION_REPEAT_THRESHOLD if min_count is None else min_count
    if len(history) < min_count:
        return None
    parsed: list[tuple[str, str]] = []
    for item in history[-min_count:]:
        entry = _parse_history_entry(item)
        if entry is None or entry[0] != "navigate":
            return None
        parsed.append((entry[1], entry[2] or ""))
    positions = {pos for _, pos in parsed}
    directions = [direction for direction, _ in parsed]
    if len(positions) != 1 or len(set(directions)) != 1:
        return None
    return directions[0]


def navigation_repeat_detected(
    history: list[str],
    *,
    min_count: int | None = None,
) -> bool:
    return repeating_nav_direction(history, min_count=min_count) is not None


def navigation_arbitration_active(stuck_count: int, state: AgentState) -> bool:
    """True when navigator should override blind path[0] (M11)."""
    history = state.get("short_term_history", [])
    return (
        stuck_count >= STUCK_ARBITRATION_THRESHOLD
        or navigation_repeat_detected(history)
        or _history_oscillates(history, min_cycles=2, max_positions=8)
    )


def _oscillation_break_step(
    gs: GameState,
    state: AgentState,
    candidates: list[str],
    path: list[str],
) -> str | None:
    """Exit a 2-tile ping-pong that never raises stuck_count (position always changes).

    Live Route 29 climb thrash (22,13↔22,14 / 27,13↔27,14) keeps forced up/down
    fighting while stuck_count stays 0. Prefer a path/candidate step that leaves
    the two-tile set.
    """
    history = list(state.get("short_term_history", []))
    if len(history) < 6:
        return None
    coords: list[tuple[int, int]] = []
    for item in history[-8:]:
        if not item.startswith("navigate:") or "@" not in item:
            return None
        _action, pos = item.split("@", 1)
        direction = _action.split(":", 1)[1]
        if direction in {"a", "b", "start", "select"}:
            continue
        parsed = _parse_history_xy(pos)
        if parsed is None:
            return None
        coords.append(parsed)
    if len(coords) < 6:
        return None
    unique = set(coords)
    if len(unique) != 2:
        return None
    if max(coords.count(c) for c in unique) < 3:
        return None
    ordered: list[str] = []
    for step in list(path[:4]) + list(candidates):
        if step in ordered or step in {"a", "b", "start", "select"}:
            continue
        if step not in candidates and step not in path[:4]:
            continue
        ordered.append(step)
    # Directions that make up the 2-tile thrash axis (e.g. up/down at 11,10↔11,11).
    # Prefer a lateral escape first — continuing path[0]="up" re-enters the pair
    # from the other tile (live egg-return thrash with stuck_count=0).
    thrash_axis: set[str] = set()
    for a, b in zip(coords, coords[1:]):
        if b[0] != a[0]:
            thrash_axis.add("left" if b[0] < a[0] else "right")
        if b[1] != a[1]:
            thrash_axis.add("up" if b[1] < a[1] else "down")
    for prefer_lateral in (True, False):
        for step in ordered:
            if step not in candidates:
                continue
            if prefer_lateral and step in thrash_axis:
                continue
            delta = _DIRECTION_DELTA.get(step)
            if delta is None:
                continue
            nx, ny = gs.player.x + delta[0], gs.player.y + delta[1]
            if (nx, ny) not in unique:
                return step
    return None


def walkable_cardinal_candidates(gs: GameState, state: AgentState | None = None) -> list[str]:
    """Adjacent walkable directions from the pathfinding grid (M4 loop expansion)."""
    grid = MAP_GRIDS.get(gs.map_key)
    session_walkable = session_walkable_for_map(state, gs.map_key)
    session_blocked = session_blocked_for_map(state, gs.map_key)
    candidates: list[str] = []
    for direction, (dx, dy) in _DIRECTION_DELTA.items():
        nx, ny = gs.player.x + dx, gs.player.y + dy
        if direction == "up" and (
            _blocked_stairs_up(gs, state)
            or (gs.map_key == MAP_KEY_ELMS_LAB and starter_quest.blocked_lab_exit(gs))
        ):
            continue
        if _is_walkable(
            grid,
            nx,
            ny,
            session_walkable=session_walkable,
            session_blocked=session_blocked,
        ):
            candidates.append(direction)
    return candidates


def expand_candidates_on_stuck(
    gs: GameState,
    candidates: list[str],
    state: AgentState,
    *,
    stuck_count: int,
) -> list[str]:
    """Add walkable cardinals when stuck or repeating so visit-aware can break loops."""
    if not navigation_arbitration_active(stuck_count, state):
        return candidates
    merged = list(candidates)
    for direction in walkable_cardinal_candidates(gs, state):
        if direction not in merged:
            merged.append(direction)
    return list(dict.fromkeys(merged))


def reorder_candidates_visit_aware(
    gs: GameState,
    candidates: list[str],
    state: AgentState,
) -> list[str]:
    """Stable reorder: higher visit-aware score first."""
    ranked = sorted(
        candidates,
        key=lambda direction: score_visit_aware_candidate(direction, gs, state),
        reverse=True,
    )
    return list(dict.fromkeys(ranked))


def visit_aware_path_step(
    path: list[str],
    gs: GameState,
    state: AgentState,
) -> str | None:
    """Best visit-aware step from an A* path prefix (M4 normal-path bias).

    Only directions that are walkable **from the current tile** may be re-ranked.
    Sequential A* paths list later steps (path[i] for i>0) that are not valid
    first moves; treating an unvisited wall-adjacent step from path[:3] as a
    first action (e.g. desk→ball after live multi-page dialog kept stuck low)
    causes permanent thrash into solids.
    """
    if not path:
        return None
    walkable = set(walkable_cardinal_candidates(gs, state))
    options: list[str] = []
    for step in path[:3]:
        if step in walkable and step not in options:
            options.append(step)
    if not options:
        return path[0]
    ranked = reorder_candidates_visit_aware(gs, options, state)
    return ranked[0] if ranked else path[0]


_FACING_TO_DIRECTION = {0: "down", 4: "up", 8: "left", 12: "right"}


def _egg_lab_desk_interact_tile(gs: GameState) -> bool:
    """True when returning the Mystery Egg and standing where Elm can be spoken to."""
    meta = gs.raw_metadata or {}
    if gs.map_key != MAP_KEY_ELMS_LAB:
        return False
    if not (meta.get("has_mystery_egg") and not meta.get("egg_delivered")):
        return False
    # Live: only (5,3) face-up completes egg delivery; (4,3) opens a non-egg dialog.
    return (gs.player.x, gs.player.y) == (5, 3)


def _interact_candidate_justified(
    gs: GameState,
    state: AgentState,
    target: tuple[int, int],
    candidates: list[str],
) -> bool:
    """True when 'a' is in candidates for ROM signal, stuck fallback, or blocked-ahead."""
    if "a" not in candidates:
        return False
    # Egg desk: never let interact-stall escape suppress A (live thrash navigate_down).
    if _egg_lab_desk_interact_tile(gs):
        clear_interact_stall_escape(state)
        return True
    if outdoor_interact_recovery_active(gs, state) or interact_stall_recovery_active(
        gs, state
    ):
        return False
    if generic_prefer_interact_candidate(gs, state) or house_exit.prefer_interact_candidate(
        gs, state
    ):
        return True
    if house_exit.stuck_interact_fallback(gs, state) or generic_stuck_interact_fallback(
        gs, state
    ):
        return True
    if (gs.player.x, gs.player.y) == target and at_target_blocked_ahead_interact_eligible(
        gs.map_key,
        gs.player.x,
        gs.player.y,
        target,
        state=state,
    ):
        return True
    return False


def select_navigation_action(
    *,
    door_exit: str | None,
    path: list[str],
    llm_choice: str | None,
    candidates: list[str],
    stuck_count: int,
    gs: GameState,
    state: AgentState,
    target: tuple[int, int],
) -> str:
    """Pick direction: door priority, stuck override, visit-aware path, LLM, fallback."""
    # Egg-return desk: hard-prefer A (after brief face-up). Live thrash stayed on
    # navigate_down/up forever while egg never delivered; (5,3)+A×50+ works.
    if _egg_lab_desk_interact_tile(gs) or (
        gs.map_key == MAP_KEY_ELMS_LAB
        and (gs.raw_metadata or {}).get("has_mystery_egg")
        and not (gs.raw_metadata or {}).get("egg_delivered")
        and gs.in_text_box
    ):
        clear_interact_stall_escape(state)
        if gs.in_text_box:
            return "a"
        need_face = "up"
        current_face = facing_to_direction(gs.player.facing)
        if current_face != need_face:
            history = list(state.get("short_term_history", []))
            face_streak = sum(
                1
                for item in list(history)[-4:]
                if item.startswith(f"navigate:{need_face}@")
            )
            if face_streak < 1:
                return need_face
        return "a"
    if door_exit:
        return door_exit
    # Outdoor soft-lock recovery (live Route 29 y=14 NPC/sign edge):
    # - Open textbox / sticky script: A advances pages; occasional B cancels menus.
    #   Prior code required *not* in_text_box for B, so residual dialog made every
    #   cardinal fail forever while B recovery never fired (B count stayed 0).
    # - Closed thrash: periodic B still clears joypad/script residue.
    meta = gs.raw_metadata or {}
    outdoor = gs.map_key not in INDOOR_NAV_STUCK_MAPS
    dialogish = bool(gs.in_text_box or meta.get("in_script") or meta.get("script_active"))
    # Same-tile streak: only run dialog A/B recovery when we are not mid-progress.
    # Live west approach (x≈9–11) wasted every other step on B while stuck stayed
    # 15–16 after each successful left (B re-inflated the meter).
    same_tile_streak = 0
    pos_tag = f"{gs.player.x},{gs.player.y}"
    for item in reversed(list(state.get("short_term_history", []))):
        if item.endswith(f"@{pos_tag}"):
            same_tile_streak += 1
        else:
            break
    # Corridor A* path commit (live thrash succeeds each step so stuck falls
    # while never progressing): egg-return south/east, and post-rival R30 north.
    # Skip a direction that has already failed twice at this tile.
    meta_egg = gs.raw_metadata or {}
    egg_return_maps = frozenset({"26:1", "26:3", "24:3"})
    egg_return = bool(
        meta_egg.get("has_mystery_egg") and not meta_egg.get("egg_delivered")
    )
    post_rival_r30_north = bool(
        state.get("starter_quest_complete")
        and gs.map_key == "26:1"
        and target[1] < gs.player.y
    )
    # Post-rival R31: commit A* west toward Violet gate (live thrash walked east).
    post_rival_r31_west = bool(
        state.get("starter_quest_complete")
        and gs.map_key == "26:2"
        and target[0] < gs.player.x
    )
    # Route 29 westbound: A* may step *east* first (y10 gap at x=28 → go via
    # x36 north bridge then west). Without path0 commit, visit-aware left/right
    # thrash at (29,10)↔(30,10) never escapes (live mid thrash post-egg).
    # Skip when a forced ledge/climb override owns this tile, or in the sign
    # pocket where left into the wall must be corrected before path0 commit.
    r29_forced = ROUTE_29_FORCED_LEDGE_STEP.get((gs.player.x, gs.player.y))
    r29_sign_trap = (
        gs.player.y in ROUTE_29_SIGN_TRAP_ROWS
        and gs.player.x <= ROUTE_29_SIGN_TRAP_MAX_X
    )
    r29_westbound = bool(
        gs.map_key == "24:3"
        and target[0] < gs.player.x
        and not egg_return  # egg-return is eastbound; covered above
        and r29_forced is None
        and not r29_sign_trap
    )
    # Violet City gym approach: A* is left/down to (18,17); visit-aware thrash
    # walked north toward (22,y) (live r31_gym / egg_gym_v2).
    violet_gym = MAP_LANDMARK_ANCHORS.get("10:5", {}).get("gym_entrance")
    violet_gym_approach = bool(
        gs.map_key == "10:5"
        and violet_gym is not None
        and target == violet_gym
    )
    # R30 north of y12: live pure-up at x2–5 fails (y11 wall; live BFS). Force
    # left into the x0–1 corridor before path0 up. At x<=1 commit path0/up north.
    # Live gym20: at x=2 y=12 left may fail → after left fails twice, path0/up.
    if (
        post_rival_r30_north
        and gs.map_key == MAP_KEY_ROUTE_30
        and gs.player.y >= 12
        and 0 <= gs.player.x <= 5
    ):
        left_fail = 0
        pos_tag_r30 = f"{gs.player.x},{gs.player.y}"
        for item in reversed(list(state.get("short_term_history", []))):
            if item == f"navigate:left@{pos_tag_r30}":
                left_fail += 1
            elif item.startswith("navigate:") and item.endswith(f"@{pos_tag_r30}"):
                continue
            else:
                break
        if "left" in candidates and gs.player.x > 1 and left_fail < 2:
            return "left"
        if path and path[0] in candidates and path[0] not in {"a", "b"}:
            return path[0]
        if "up" in candidates:
            return "up"
        return "left" if "left" in candidates else "up"
    # Egg-return R29: live walk (bedroom_egg_r29) is south via y11–12 then y14
    # east — not north into y7–8 sign soft-lock. Before path0 (A* still prefers up).
    # At (11,11) pure-down fails (live manual walk) — after one fail, go right.
    # At y=12 x14–15 visit-aware L/R thrash (live gym12) — force right east.
    if (
        egg_return
        and gs.map_key == MAP_KEY_ROUTE_29
        and not gs.in_text_box
    ):
        # Live corridor (bedroom_egg_r29 BFS): y10 pocket east is solid until y12
        # bridge x16–17; then y14 east; at x≥48 climb north to (59,8).
        pos_tag_er = f"{gs.player.x},{gs.player.y}"

        def _fail_count(direction: str) -> int:
            n = 0
            for item in reversed(list(state.get("short_term_history", []))):
                if item == f"navigate:{direction}@{pos_tag_er}":
                    n += 1
                elif item.startswith("navigate:") and item.endswith(f"@{pos_tag_er}"):
                    continue
                else:
                    break
            return n

        if gs.player.x < 55:
            if gs.player.y < 12:
                # Get to y12 bridge before pushing east into y10 wall x16+.
                if "down" in candidates and _fail_count("down") < 2:
                    return "down"
                if "right" in candidates and _fail_count("right") < 2:
                    return "right"
            elif gs.player.y <= 16:
                if "right" in candidates and _fail_count("right") < 3:
                    return "right"
                if "up" in candidates and gs.player.x >= 48 and gs.player.y > 8:
                    return "up"
                if "down" in candidates and gs.player.x < 40 and _fail_count("down") < 2:
                    return "down"
                if "right" in candidates:
                    return "right"
    # Keep A* path0 commit even when thrash raised stuck_count (was stuck < 8).
    # Live bed_chain_gym: thrash meter hit 8–9 then path0 dropped and agent
    # wandered south on R30 instead of committing north to R31.
    # Never path0-walk over an open outdoor textbox (rival multi-page dialog).
    if (
        outdoor
        and path
        and path[0] in candidates
        and path[0] not in {"a", "b", "start", "select"}
        and not gs.in_text_box
        and (
            (egg_return and gs.map_key in egg_return_maps)
            or post_rival_r30_north
            or post_rival_r31_west
            or r29_westbound
            or violet_gym_approach
        )
    ):
        path0_fail = 0
        pos_tag_egg = f"{gs.player.x},{gs.player.y}"
        for item in reversed(list(state.get("short_term_history", []))):
            if item == f"navigate:{path[0]}@{pos_tag_egg}":
                path0_fail += 1
            elif item.startswith("navigate:") and item.endswith(f"@{pos_tag_egg}"):
                continue
            else:
                break
        # Allow more path0 retries when thrash-elevated stuck (soft walls / dialog).
        # R31 westbound needs a longer budget: tree-edge false fails + NPC grass
        # made budget=2 drop into visit-aware L/R thrash (live gym26 x24 pocket).
        # Egg-return R29 east: A-spam at (32,6)/(36,8) SCRIPT_READ then hard-reload
        # (live bed_egg_to_gym1) — keep path0 right longer before recovery A.
        if post_rival_r31_west or (
            gs.map_key == MAP_KEY_ROUTE_31 and target[0] < gs.player.x
        ):
            path0_budget = 6 if stuck_count >= 4 else 4
        elif egg_return and gs.map_key in egg_return_maps:
            path0_budget = 8 if stuck_count >= 4 else 5
        else:
            path0_budget = 4 if stuck_count >= 8 else 2
        if path0_fail < path0_budget:
            return path[0]
        for step in path[1:6]:
            if step in candidates and step not in {"a", "b"}:
                return step
    # Egg-return eastbound on R29: live BFS uses south y14 corridor first.
    # Force down while still north of y14 (live gym7 thrash up at (17,7)).
    if (
        egg_return
        and gs.map_key == MAP_KEY_ROUTE_29
        and not gs.in_text_box
    ):
        if gs.player.y < 14 and "down" in candidates and target[1] >= gs.player.y:
            return "down"
        if target[0] > gs.player.x and "right" in candidates:
            return "right"
    # Outdoor soft-lock recovery: engage earlier when thrash raised stuck
    # (was stuck>=8; live R30 textbox pin never left interact to use this).
    if outdoor and stuck_count >= 4 and same_tile_streak >= 1:
        # After long soft-lock, still try path movement every third step even if
        # script flags are sticky (live R30 (13,24) A/B forever with in_script).
        if stuck_count >= 20 and stuck_count % 3 == 0 and not gs.in_text_box:
            pass  # fall through to path / candidates (never abandon open textbox)
        elif gs.in_text_box:
            # Open outdoor textbox: prefer pure A (B can hard-lock SCRIPT_READ).
            # Exception: frozen outdoor dialog (script_pos never advances) — rare B
            # (live R31 (18,12): 200×A alone never clears; runner stuck++ at 40).
            frozen = int(state.get("outdoor_script_frozen_count", 0))
            if frozen >= 30 and frozen % 8 == 0:
                return "b"
            return "a"
        elif dialogish and path and path[0] in candidates and (
            post_rival_r30_north
            or post_rival_r31_west
            or r29_westbound
            or (egg_return and gs.map_key in egg_return_maps)
        ):
            # Sticky outdoor script without open textbox: pure A never clears
            # (live gym30 (1,10) navigate_a×N then hard-reload). Prefer A* leave.
            # Egg-return R29: same class at (17,5)/(32,6)/(36,8) (bed_egg_to_gym1).
            return path[0]
        elif dialogish and egg_return and gs.map_key in egg_return_maps:
            # Sticky script on egg-return: never pure-A outdoors — walk path or
            # cardinals instead (A re-triggers SCRIPT_READ soft-lock).
            if path and path[0] in candidates and path[0] not in {"a", "b"}:
                return path[0]
            for step in ("right", "up", "down", "left"):
                if step in candidates:
                    return step
            if stuck_count % 7 == 0:
                return "b"
            return "a"
        elif dialogish:
            # Closed textbox but sticky script: prefer A; rare B for menu residue.
            if stuck_count % 7 == 0:
                return "b"
            return "a"
        elif egg_return and gs.map_key in egg_return_maps:
            # No dialog flags but stuck outdoor egg-return: still never A
            # (live gym7 (17,7) navigate_a×N → hard-reload).
            if path and path[0] in candidates and path[0] not in {"a", "b"}:
                return path[0]
            for step in ("right", "up", "down", "left"):
                if step in candidates:
                    return step
        elif stuck_count % 5 == 3:
            return "b"
        # Hard soft-lock: no dialog flags but every cardinal still fails.
        elif stuck_count >= 12 and stuck_count % 3 == 0:
            return "b"
    # Egg-return outdoor: never justify interact A on residual (17,5)/(17,7).
    if egg_return and outdoor and gs.map_key in egg_return_maps and not gs.in_text_box:
        pass  # skip _interact_candidate_justified A
    elif _interact_candidate_justified(gs, state, target, candidates):        # Face the interactable (e.g. Elm balls north of approach) before A.
        # Live Silver often reports non-pret facing bytes (None here). Still try a
        # few face presses so A is not always held sideways; after a short streak
        # of the same face attempt, press A so invalid facing cannot soft-lock.
        need_face = interact_face_direction(
            gs.map_key, gs.player.x, gs.player.y, target, state=state
        )
        current_face = facing_to_direction(gs.player.facing)
        if need_face is not None and current_face != need_face:
            history = list(state.get("short_term_history", []))
            face_streak = 0
            for item in reversed(history):
                if item.startswith(f"navigate:{need_face}@"):
                    face_streak += 1
                else:
                    break
            if face_streak < 3:
                return need_face
        return "a"
    # Forced ledge steps apply even when A* returns empty (session blocks).
    # Only honor the forced step when that direction is currently a candidate
    # (walkable) so we never drive into grid solids (e.g. left at 23,12).
    # When arbitrating, skip a forced direction that is the repeating failed press
    # so we can fall through to A*/candidate re-rank (live 40,14 left thrash).
    forced_ledge = ROUTE_29_FORCED_LEDGE_STEP.get((gs.player.x, gs.player.y))
    arbitrate_early = navigation_arbitration_active(stuck_count, state)
    repeat_dir_early = (
        repeating_nav_direction(state.get("short_term_history", []))
        if arbitrate_early
        else None
    )
    # Climb-row "up" must not override A* *lateral* west detours (live
    # 27,13↔27,14: force-up on y=14 fought force-down on y=13 with stuck=0).
    climb_lateral = (
        forced_ledge == "up"
        and path
        and path[0] in ("left", "right")
        and path[0] in candidates
    )
    honor_forced = (
        gs.map_key == MAP_KEY_ROUTE_29
        and forced_ledge is not None
        and forced_ledge in candidates
        and forced_ledge != repeat_dir_early
        and not climb_lateral
    )
    # 2-tile force fights never increment stuck; break when forced step would
    # stay inside the thrash pair. East-ledge force-down still wins when it is
    # the escape (or when there is no oscillation).
    if _history_oscillates(
        list(state.get("short_term_history", [])), min_cycles=2, max_positions=2
    ):
        break_step = _oscillation_break_step(gs, state, candidates, path)
        if break_step is not None:
            if not honor_forced:
                return break_step
            delta = _DIRECTION_DELTA.get(forced_ledge or "")
            if delta is not None:
                nx, ny = gs.player.x + delta[0], gs.player.y + delta[1]
                # Parse thrash set from recent history positions
                thrash_set: set[tuple[int, int]] = set()
                for item in list(state.get("short_term_history", []))[-8:]:
                    if item.startswith("navigate:") and "@" in item:
                        parsed = _parse_history_xy(item.split("@", 1)[1])
                        if parsed is not None:
                            thrash_set.add(parsed)
                # Only break forced climb up/down west of the east ledge pocket.
                # East-ledge force-down must still escape the (44,y) thrash south.
                if (
                    (nx, ny) in thrash_set
                    and forced_ledge in {"up", "down"}
                    and gs.player.x < ROUTE_29_EAST_LEDGE_FORCE_MIN_X
                ):
                    return break_step
    if honor_forced:
        # If the forced step has already failed twice at this tile, take the next
        # path/candidate exit (live (38,15) force-down into NPC after dialog).
        pos_tag = f"{gs.player.x},{gs.player.y}"
        forced_fails = 0
        for item in reversed(list(state.get("short_term_history", []))):
            if item == f"navigate:{forced_ledge}@{pos_tag}":
                forced_fails += 1
            elif item.startswith("navigate:") and item.endswith(f"@{pos_tag}"):
                continue
            else:
                break
        if forced_fails < 2:
            return forced_ledge
        for step in list(path[:4]) + list(candidates):
            if (
                step in candidates
                and step not in {forced_ledge, "a", "b", "start", "select"}
                and step != repeat_dir_early
            ):
                return step
        return forced_ledge
    if path:
        trap_step = _route_29_sign_dead_end_path_step(gs, path, target)
        if trap_step is not None and trap_step != repeat_dir_early:
            return trap_step
        y16_step = _route_29_y16_corridor_path_step(gs, path, target)
        if y16_step is not None and y16_step != repeat_dir_early:
            return y16_step
        west_row_step = _route_29_west_row_path_step(gs, target, path)
        if west_row_step is not None and west_row_step != repeat_dir_early:
            return west_row_step
        corridor_step = _route_29_south_corridor_path_step(gs, target, path)
        # Corridor helper returns path[0] near reentry; still honor skip-repeat so
        # arbitration tests (and live thrash) can pivot to path[1:].
        if corridor_step is not None and corridor_step != repeat_dir_early:
            return corridor_step
        ledge_step = _route_29_ledge_path_step(gs, target, path)
        if ledge_step is not None and ledge_step != repeat_dir_early:
            return ledge_step
        # West of Route 29 mid-corridor: follow A* to Cherrygrove edge / south-gap
        # strictly (LLM thrash at x≈10 y≈6–8 blocked the west handoff).
        # Still honor skip-repeat / stuck so path[0]="left" cannot soft-lock forever
        # into an NPC (live (35,7) left×N with stuck climbing past 15).
        west_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit")
        west_south_gap = (4, 10)
        west_target = target in (west_exit, west_south_gap)
        # On the open y=10 west-gap row, commit left first. A* to (4,10) can
        # start with "down" into (11,11) then flip target back to the gate → thrash.
        if (
            gs.map_key == MAP_KEY_ROUTE_29
            and west_target
            and gs.player.y == 10
            and gs.player.x > 4
            and "left" in candidates
            and "left" != repeat_dir_early
            and stuck_count < 4
        ):
            return "left"
        # Near the x=8 wall on the north corridor (x≈8–16, y<10): go south to the
        # y=10 gap first. Do NOT apply map-wide for x≥8 — that forced down at
        # (35,7) during the open north strip west detour (live soft-lock).
        if (
            gs.map_key == MAP_KEY_ROUTE_29
            and west_target
            and 8 <= gs.player.x <= 16
            and gs.player.y < 10
            and "down" in candidates
            and "down" != repeat_dir_early
            and stuck_count < 4
        ):
            return "down"
        if (
            gs.map_key == MAP_KEY_ROUTE_29
            and west_target
            and path
            and path[0] in candidates
            and path[0] != repeat_dir_early
            and stuck_count < 4
        ):
            return path[0]
        # Stuck on west handoff: skip path[0] (often left into NPC) and any
        # identical prefix; try other path steps then walkable candidates.
        if (
            gs.map_key == MAP_KEY_ROUTE_29
            and west_target
            and stuck_count >= 4
            and path
        ):
            blocked = {path[0], repeat_dir_early, "a", "b"}
            for step in path[:8]:
                if step in candidates and step not in blocked:
                    return step
            for step in candidates:
                if step not in blocked and step is not None:
                    return step
    arbitrate = navigation_arbitration_active(stuck_count, state)
    repeat_dir = (
        repeating_nav_direction(state.get("short_term_history", [])) if arbitrate else None
    )
    if arbitrate and path:
        for path_step in path[:4]:
            if path_step in candidates and path_step != repeat_dir:
                return path_step
    if (
        arbitrate
        and llm_choice
        and llm_choice in candidates
        and llm_choice != repeat_dir
    ):
        return llm_choice
    if arbitrate:
        pool = [c for c in candidates if c not in {"a", repeat_dir}]
        if pool:
            ranked = reorder_candidates_visit_aware(gs, pool, state)
            if ranked and ranked[0] != "a":
                return ranked[0]
    # Route 29: prefer A* first step over pure visit-aware re-rank (climb thrash).
    if (
        gs.map_key == MAP_KEY_ROUTE_29
        and path
        and path[0] in candidates
        and path[0] != repeat_dir
    ):
        return path[0]
    # Route 31 west to Violet: never visit-aware re-rank A* (live thrash walked
    # left/right in the x24 pocket while path0 was down/right around trees).
    if (
        gs.map_key == MAP_KEY_ROUTE_31
        and path
        and path[0] in candidates
        and path[0] != repeat_dir
        and target[0] < gs.player.x
    ):
        return path[0]
    if path:
        return visit_aware_path_step(path, gs, state) or path[0]
    if llm_choice and llm_choice in candidates and llm_choice != "a":
        return llm_choice
    toward = direction_toward(gs.player.x, gs.player.y, target[0], target[1])
    if toward != "a":
        return toward
    for step in candidates:
        if step != "a":
            return step
    return "down"


def _capture_stuck_episode(state: AgentState, gs: GameState) -> None:
    try:
        _long_term_memory().capture_stuck_episode(state, gs)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not capture stuck episode: %s", exc)


def _attach_landmark_context(state: AgentState, gs: GameState) -> list[dict[str, Any]]:
    landmarks = list(state.get("known_landmarks", []))
    query = f"{gs.map_key} {gs.player.map_name} {state.get('active_subgoal', '')}"
    relevant = retrieve_landmarks_from_state(landmarks, query, k=3)
    formatted = format_landmarks_for_prompt(relevant)
    if formatted:
        retrievals = list(state.get("memory_retrievals", []))
        if formatted not in retrievals:
            retrievals.append(formatted)
        state["memory_retrievals"] = retrievals[-5:]
    return relevant


def _persist_landmark_discoveries(state: AgentState, discoveries: list[dict[str, Any]]) -> None:
    if not discoveries:
        return
    apply_landmark_discovery(state, discoveries)
    try:
        memory = _long_term_memory()
        for landmark in discoveries:
            memory.add_landmark(landmark)
            logger.info(
                "Landmark discovered: %s at %s (%s,%s)",
                landmark.get("name"),
                landmark.get("map_key"),
                landmark.get("x"),
                landmark.get("y"),
            )
    except OSError as exc:
        logger.warning("Could not persist landmarks: %s", exc)


EARLY_GAME_OBJECTIVES = {
    MAP_KEY_PLAYERS_HOUSE_2F: "Leave bedroom via stairs, talk to Mom on 1F, then head to Professor Elm",
    MAP_KEY_PLAYERS_HOUSE_1F: "Talk to Mom and leave through the front door to New Bark Town",
    MAP_KEY_NEW_BARK_TOWN: "Visit Professor Elm's lab and choose a starter Pokemon",
    "24:5": "Talk to Elm, choose a starter Pokemon, receive Potion",
    MAP_KEY_ROUTE_29: "Travel west through Route 29 toward Cherrygrove City",
    MAP_KEY_ROUTE_30: "Travel Route 30 toward Route 31 and Violet City",
    MAP_KEY_ROUTE_31: "Cross Route 31 west into Violet City",
    MAP_KEY_CHERRYGROVE_CITY: "Leave Cherrygrove north toward Route 30/31 and Violet City",
    MAP_KEY_MR_POKEMONS_HOUSE: "Talk to Mr. Pokemon and receive the Mystery Egg from Oak",
    MAP_KEY_VIOLET_CITY: "Find and enter Violet Gym (first gym)",
    MAP_KEY_VIOLET_GYM: "First gym reached — challenge Falkner when ready",
    "26:10": "Talk to Mr. Pokemon and receive the Mystery Egg from Oak",
}


def _hold_phase_satisfied(gs: GameState, state: AgentState) -> bool:
    """Terminal idle only when the active early-game phase goal is complete."""
    if not state.get("house_exit_complete"):
        return house_exit.is_satisfied(gs, state)
    if not state.get("starter_quest_complete"):
        return starter_quest.is_satisfied(gs, state)
    return early_progression.is_satisfied(gs, state)


def supervisor_node(state: AgentState) -> AgentState:
    """Route to appropriate specialist based on game phase."""
    gs = GameState.model_validate(state.get("game_state", {}))

    if needs_bootstrap(gs, state):
        state["next_node"] = "bootstrap"
        state["phase"] = "bootstrap"
    elif _hold_phase_satisfied(gs, state):
        state["next_node"] = "idle"
        if not state.get("house_exit_complete"):
            state["phase"] = "house_exit_done"
        elif state.get("starter_quest_complete"):
            state["phase"] = "early_progression_done"
        else:
            state["phase"] = "starter_quest_done"
    elif gs.battle.in_battle:
        state["next_node"] = "battler"
        state["phase"] = "battle"
    elif state.get("should_replan"):
        # Outdoor thrash can pin planner↔interact forever after stuck threshold
        # (live bed_chain_gym4 at R30 12,14 stuck=11). Cap replan loops then
        # force navigator so path0 / outdoor recovery can move again.
        outdoor = gs.map_key not in INDOOR_NAV_STUCK_MAPS
        stuck_n = int(state.get("stuck_count", 0))
        if outdoor and stuck_n >= STUCK_THRESHOLD:
            loops = int(state.get("stuck_replan_loops", 0)) + 1
            state["stuck_replan_loops"] = loops
            if loops >= 2:
                state["next_node"] = "navigator"
                state["should_replan"] = False
                state["stuck_replan_loops"] = 0
                state["phase"] = "explore"
            else:
                state["next_node"] = "planner"
        else:
            state["stuck_replan_loops"] = 0
            state["next_node"] = "planner"
    elif needs_interaction(gs, state):
        # Outdoor frozen textbox: pure A can pin the supervisor on interactor for
        # hundreds of steps while stuck stays mid-range (live R30 10,19). After a
        # long freeze + elevated stuck, break out to navigator recovery / path0.
        outdoor = gs.map_key not in INDOOR_NAV_STUCK_MAPS
        frozen = int(state.get("outdoor_script_frozen_count", 0))
        stuck_n = int(state.get("stuck_count", 0))
        no_prog = int(state.get("interact_no_progress_count", 0))
        # Route 31 westbound: never open interactor for residual in_script without
        # a live textbox — A at (18,14) soft-locks SCRIPT_READ (live gym27/40).
        # Keep pure path0 walking through the mid connector.
        r31_west_no_a = (
            outdoor
            and gs.map_key == MAP_KEY_ROUTE_31
            and state.get("starter_quest_complete")
            and not gs.in_text_box
        )
        # Egg-return / R29 outdoor: never pin on interactor without open textbox.
        # Live bed_egg_to_gym1–3: residual in_script A-spam; post-egg westbound
        # gym19: (50,11) interact_a/navigate_a thrash after egg delivery.
        # Require not in_text_box so Cherrygrove rival multi-page dialog stays
        # on interactor (A-only) until the box closes.
        meta_sup = gs.raw_metadata or {}
        egg_return_no_a = (
            outdoor
            and not gs.in_text_box
            and bool(meta_sup.get("has_mystery_egg") and not meta_sup.get("egg_delivered"))
            and gs.map_key in ("24:3", "26:1", "26:3")
        )
        r29_west_no_a = (
            outdoor
            and gs.map_key == MAP_KEY_ROUTE_29
            and not gs.in_text_box
            and (
                state.get("starter_quest_complete")
                or bool(meta_sup.get("egg_delivered"))
            )
        )
        # Break interact pin sooner on *closed* outdoor residue. Live bed_chain
        # gym6/13 stuck stayed 0 while interact_a spammed sticky SCRIPT_READ.
        # Do not force navigator while an open textbox still needs pure A
        # (rival / multi-page outdoor dialog; freeze counters climb on same-tile A).
        closed_outdoor_residue = outdoor and not gs.in_text_box
        if outdoor and (
            r31_west_no_a
            or egg_return_no_a
            or r29_west_no_a
            or (
                closed_outdoor_residue
                and (
                    (stuck_n >= 4 and (frozen >= 4 or stuck_n >= 5))
                    or frozen >= 5
                    or no_prog >= 6
                )
            )
        ):
            state["next_node"] = "navigator"
            state["phase"] = "explore"
            state["should_replan"] = True
        else:
            state["next_node"] = "interactor"
            state["phase"] = "interact"
    elif needs_script_wait(gs, state):
        state["next_node"] = "waiter"
        state["phase"] = "wait"
    elif house_exit.force_interactor(gs, state) or (
        generic_force_interactor(gs, state)
        and not outdoor_interact_recovery_active(gs, state)
    ):
        state["next_node"] = "interactor"
        state["phase"] = "interact"
    elif state.get("stuck_count", 0) >= STUCK_THRESHOLD:
        state["next_node"] = "planner"
        state["should_replan"] = True
    elif state.get("phase") == "plan":
        state["next_node"] = "planner"
    else:
        state["next_node"] = "navigator"

    if state["next_node"] == "navigator":
        if state.get("starter_quest_complete") and not early_progression.is_satisfied(gs, state):
            state["phase"] = "early_progression"
        elif state.get("house_exit_complete") and not state.get("starter_quest_complete"):
            state["phase"] = "starter_quest"
    elif state["next_node"] == "planner" and state.get("starter_quest_complete"):
        state["phase"] = "early_progression"
    elif state["next_node"] == "battler" and state.get("starter_quest_complete"):
        state["phase"] = "early_progression"

    logger.debug("Supervisor routing to %s", state["next_node"])
    return state


def _valid_script_mode(mode: int) -> bool:
    return mode in (SCRIPT_READ, SCRIPT_WAIT_MOVEMENT, SCRIPT_WAIT)


def needs_script_wait(gs: GameState, state: dict | None = None) -> bool:
    """True when a map script is running movement/timing steps (no button input)."""
    state = state or {}
    if gs.battle.in_battle or needs_bootstrap(gs, state):
        return False
    if state.get("post_warp_wait_steps", 0) > 0:
        return True
    meta = gs.raw_metadata or {}
    mode = meta.get("script_mode", 0)
    script_active = bool(meta.get("script_flags", 0) & SCRIPT_FLAG_SCRIPT_RUNNING)
    if not _valid_script_mode(mode):
        return False
    if mode in (SCRIPT_WAIT_MOVEMENT, SCRIPT_WAIT) and script_active:
        return True
    return False


def needs_interaction(gs: GameState, state: dict | None = None) -> bool:
    """True when ROM signals expect A/B dialog input instead of movement."""
    state = state or {}
    if gs.battle.in_battle or needs_bootstrap(gs, state):
        return False
    if needs_script_wait(gs, state):
        return False
    starter_quest.ensure_house_exit_complete(gs, state)
    # Phase-forced scenes (MeetMom) beat stall recovery — movement is locked.
    if house_exit.needs_house_interaction(gs, state):
        return True
    if outdoor_interact_recovery_active(gs, state) or interact_stall_recovery_active(
        gs, state
    ):
        return False
    return generic_is_interact_needed(gs, state)


def _tick_post_warp_wait(state: AgentState) -> None:
    remaining = state.get("post_warp_wait_steps", 0)
    if remaining > 0:
        state["post_warp_wait_steps"] = remaining - 1


def waiter_node(state: AgentState) -> AgentState:
    """Advance scripted movement by ticking frames without joypad input."""
    gs = GameState.model_validate(state.get("game_state", {}))
    _tick_post_warp_wait(state)
    state["last_action"] = "wait_script"
    state["last_action_result"] = {
        "script_mode": (gs.raw_metadata or {}).get("script_mode"),
        "script_running": (gs.raw_metadata or {}).get("script_running"),
        "post_warp_remaining": state.get("post_warp_wait_steps", 0),
    }
    state["position_before_action"] = gs.position_key
    state["facing_before_action"] = gs.player.facing
    state["next_node"] = "critic"
    return state


def interactor_node(state: AgentState) -> AgentState:
    """Advance dialog and scripted indoor scenes with A/B."""
    gs = GameState.model_validate(state.get("game_state", {}))
    _tick_post_warp_wait(state)
    idx = state.get("interact_action_index", 0)
    frozen = int(state.get("outdoor_script_frozen_count", 0))
    outdoor = gs.map_key not in INDOOR_NAV_STUCK_MAPS
    # Frozen outdoor textbox: pure A never advances (live R31 18,12/18,13).
    # Fire rare B earlier so soft-locks escape before 200-step interact thrash.
    if outdoor and gs.in_text_box and frozen >= 20 and frozen % 6 == 0:
        button = "b"
    elif generic_is_interact_needed(gs, state):
        button = "a"
    else:
        button = "a" if idx % 8 != 7 else "b"
    state["interact_action_index"] = idx + 1
    state["last_action"] = f"interact_{button}"
    state["last_action_result"] = {"button": button, "interact_index": idx}
    state["position_before_action"] = gs.position_key
    state["facing_before_action"] = gs.player.facing
    history = list(state.get("short_term_history", []))
    history.append(f"interact:{button}@{gs.player.x},{gs.player.y}")
    state["short_term_history"] = history[-20:]
    state["next_node"] = "critic"
    return state


def bootstrap_node(state: AgentState) -> AgentState:
    """Press through title screens, dialogs, name entry, and clock setup."""
    gs = GameState.model_validate(state.get("game_state", {}))
    idx = state.get("bootstrap_action_index", 0)
    loaded_map = None
    if gs.player.map_group or gs.player.map_id:
        loaded_map = (gs.player.map_group, gs.player.map_id)
    button = pick_bootstrap_button(idx, loaded_map=loaded_map)
    state["bootstrap_action_index"] = idx + 1
    state["last_action"] = f"bootstrap_{button}"
    state["last_action_result"] = {"button": button, "bootstrap_index": idx}
    state["position_before_action"] = gs.position_key
    history = list(state.get("short_term_history", []))
    history.append(f"bootstrap:{button}@{gs.player.x},{gs.player.y}")
    state["short_term_history"] = history[-20:]
    state["next_node"] = "critic"
    return state


def idle_node(state: AgentState) -> AgentState:
    """Terminal phase state: no further navigation input."""
    gs = GameState.model_validate(state.get("game_state", {}))
    if early_progression.is_satisfied(gs, state):
        action = early_progression.EARLY_PROGRESSION_DONE_ACTION
        reason = "early_progression_satisfied"
    elif starter_quest.is_satisfied(gs, state):
        action = starter_quest.STARTER_QUEST_DONE_ACTION
        reason = "starter_quest_satisfied"
    else:
        action = house_exit.HOUSE_EXIT_DONE_ACTION
        reason = "house_exit_satisfied"
    state["last_action"] = action
    state["last_action_result"] = {"reason": reason, "map_key": gs.map_key}
    state["position_before_action"] = gs.position_key
    state["next_node"] = "critic"
    return state


def planner_node(state: AgentState) -> AgentState:
    """Hierarchical planning: LLM-assisted subgoals with heuristic fallback."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key
    relevant_landmarks = _attach_landmark_context(state, gs)

    objective = EARLY_GAME_OBJECTIVES.get(map_key, "Explore and progress story")
    subgoals = _decompose_subgoals(gs, state)

    llm_result = None
    allows_llm = house_exit.planner_allows_llm(gs, state)
    if state.get("house_exit_complete"):
        allows_llm = allows_llm and starter_quest.planner_allows_llm(gs, state)
    if state.get("starter_quest_complete"):
        allows_llm = allows_llm and early_progression.planner_allows_llm(gs, state)
    if allows_llm:
        llm_result = llm_plan(gs, state, relevant_landmarks)
    if llm_result and llm_result.get("subgoals"):
        subgoals = llm_result["subgoals"]
        state["memory_retrievals"] = [llm_result.get("llm_plan", "")]
    else:
        state["memory_retrievals"] = []

    plan = [
        f"Current area: {gs.player.map_name}",
        objective,
        f"Active subgoal: {state.get('active_subgoal', 'explore')}",
    ]
    state["current_plan"] = plan
    state["subgoals"] = subgoals
    if subgoals:
        replan_count = state.get("replan_count", 0)
        idx = min(replan_count, len(subgoals) - 1)
        state["active_subgoal"] = subgoals[idx]

    state["should_replan"] = False
    state["last_action"] = "plan_replan"
    state["last_action_result"] = {"subgoals": subgoals}
    outdoor = gs.map_key not in INDOOR_NAV_STUCK_MAPS
    stuck_n = int(state.get("stuck_count", 0))
    # Do not re-pin outdoor thrash into interactor after replan (live R30 12,15
    # planner→interact_a forever). Navigator recovery clears dialog with A/B.
    outdoor_thrash_escape = outdoor and stuck_n >= 5
    if (
        not outdoor_thrash_escape
        and (
            house_exit.force_interactor(gs, state)
            or (
                generic_is_interact_needed(gs, state)
                and not outdoor_interact_recovery_active(gs, state)
                and not interact_stall_recovery_active(gs, state)
            )
        )
    ):
        state["phase"] = "interact"
        state["next_node"] = "interactor"
        starter_quest.sync_subgoals(gs, state)
        return state
    state["phase"] = "explore"
    state["next_node"] = "navigator"
    return state


def _decompose_subgoals(gs: GameState, state: AgentState | None = None) -> list[str]:
    state = state or {}
    house = house_exit.decompose_subgoals(gs)
    if house:
        return house
    if state.get("house_exit_complete") and not state.get("starter_quest_complete"):
        quest = starter_quest.decompose_subgoals(gs)
        if quest:
            return quest
    if state.get("starter_quest_complete"):
        progress = early_progression.decompose_subgoals(gs)
        if progress:
            return progress
    if gs.battle.in_battle:
        return ["Win battle or run if low HP"]
    return ["Explore current map", "Progress toward next town"]


def _players_house_door_exit(gs: GameState, state: AgentState | None = None) -> str | None:
    state = state or {}
    door: tuple[int, int] | None = None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        entrance = find_landmark(
            state.get("known_landmarks", []),
            landmark_id=ELMS_LAB_ENTRANCE_ID,
        )
        if entrance is not None and entrance.get("map_key") == gs.map_key:
            door = landmark_coords(entrance)
    lab_exit = starter_quest.door_exit_direction(gs, door=door)
    if lab_exit:
        return lab_exit
    house_door = house_exit.door_exit_direction(gs)
    if house_door:
        return house_door
    from src.graph.exploration import exploration_heading_west
    from src.graph.pathfinding import map_edge_exit_direction

    # Map-edge warps (Cherrygrove north → R30, R29 west → Cherry, R30 south → Cherry).
    # Suppress edge presses that fight the current quest target:
    # - Egg-return on Cherrygrove east: do not force north "up" back to R30.
    # - Egg-return on New Bark lab: do not force west "left" back to R29
    #   (live thrash 24:4:0:8 ↔ 24:3:59:8).
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS
    from src.graph.navigation_resolve import resolve_navigation_target

    target = resolve_navigation_target(gs, state)
    anchors = MAP_LANDMARK_ANCHORS.get(gs.map_key, {})
    east = anchors.get("east_exit")
    west = anchors.get("west_exit")
    heading_east = east is not None and target == east
    # Egg-return eastbound on R29/Cherry: target may be east_exit or further east.
    meta_edge = gs.raw_metadata or {}
    if (
        not heading_east
        and target is not None
        and target[0] > gs.player.x
        and meta_edge.get("has_mystery_egg")
        and not meta_edge.get("egg_delivered")
        and gs.map_key in ("24:3", "26:3")
    ):
        heading_east = True
    lab = find_landmark(
        list(state.get("known_landmarks", [])), landmark_id=ELMS_LAB_ENTRANCE_ID
    )
    lab_xy = landmark_coords(lab) if lab is not None else anchors.get("elms_lab_door")
    # Lab approach may be (6,4) while door anchor is (6,3) — both count.
    lab_door = anchors.get("elms_lab_door") or (6, 3)
    heading_lab = target in {lab_xy, lab_door, (6, 3), (6, 4), (5, 3), (5, 4)} or (
        lab_xy is not None and target is not None and abs(target[0] - lab_door[0]) <= 2
        and abs(target[1] - lab_door[1]) <= 2
        and gs.map_key == "24:4"
    )
    heading_west = exploration_heading_west(gs, state) and not heading_east and not heading_lab
    # Also treat a resolved west_exit target as westbound (R29 entry at y=8 while
    # west warp-hint row is y=7 — exploration_heading_west alone can miss).
    if (
        not heading_west
        and not heading_east
        and not heading_lab
        and west is not None
        and target is not None
        and target[0] <= west[0] + 1
        and target[0] < gs.player.x
    ):
        heading_west = True
    north = anchors.get("north_exit")
    south = anchors.get("south_exit")
    heading_north = bool(
        north is not None
        and target is not None
        and target == north
        or (
            target is not None
            and north is not None
            and target[1] <= north[1]
            and target[1] < gs.player.y
        )
    )
    # Route 30 post-rival: target is route_31_gate (north), not south_exit.
    heading_south = bool(
        south is not None
        and target is not None
        and (
            target == south
            or (target[1] >= south[1] and target[1] > gs.player.y)
        )
    )
    # R30 northbound: target y less than player (route_31_gate at y=0).
    if (
        not heading_north
        and not heading_south
        and target is not None
        and target[1] < gs.player.y
        and abs(target[0] - gs.player.x) <= 12
    ):
        heading_north = True
    edge = map_edge_exit_direction(
        gs,
        heading_west=heading_west,
        heading_east=heading_east,
        heading_south=heading_south,
        heading_north=heading_north,
    )
    if edge is not None:
        if heading_east and edge in ("up", "left"):
            pass  # do not bounce west/north while egg-returning east
        elif heading_lab and edge == "left":
            pass  # keep moving toward Elm's lab
        elif heading_north and edge == "down":
            pass  # do not bounce back south when northbound on R30
        else:
            return edge
    # Standing on a north/south/east exit landmark with empty A* path: step off-map
    # only when heading that way (avoid re-entering the map we just left).
    if heading_north and north is not None and (
        (gs.player.x, gs.player.y) == north
        or (
            gs.player.y == north[1]
            and abs(gs.player.x - north[0]) <= 2
        )
    ):
        return "up"
    # Route 30 → Route 31: route_31_gate anchor is the north map edge.
    r31 = anchors.get("route_31_gate")
    if (
        r31 is not None
        and gs.player.y == r31[1]
        and abs(gs.player.x - r31[0]) <= 2
        and target is not None
        and (target == r31 or target[1] <= r31[1])
    ):
        return "up"
    # Only force down when standing on the south exit tile (or same x).
    # Lab exit (4,11): standing at (3,11) must step right first — abs(dx)<=1
    # incorrectly forced down into the wall (live thrash after starter).
    if (
        heading_south
        and south is not None
        and gs.player.y == south[1]
        and gs.player.x == south[0]
    ):
        return "down"
    # Route 31 Violet gate: standing on west_gate (4,6)/(4,7) must press left
    # (live ended on (4,7) thrashing up/right because A* path is empty at goal).
    r31_gate = anchors.get("west_gate")
    if (
        r31_gate is not None
        and target is not None
        and target == r31_gate
        and gs.player.x == r31_gate[0]
        and abs(gs.player.y - r31_gate[1]) <= 1
    ):
        return "left"
    # East edge only when intentionally heading east (egg-return Cherry→R29).
    if (
        heading_east
        and east is not None
        and gs.player.x == east[0]
        and abs(gs.player.y - east[1]) <= 1
    ):
        return "right"
    # Gate / map west_exit when standing on that tile (R31 Violet Gate → Violet).
    # Require same row as west_exit so we do not force "left" one tile north of
    # New Bark west_exit (0,8) — that blocked the down step from (0,7).
    if (
        west is not None
        and target is not None
        and target == west
        and gs.player.x <= west[0] + 1
        and gs.player.y == west[1]
    ):
        return "left"
    return None


def _east_corridor_blocked_ahead(gs: GameState, state: AgentState) -> bool:
    """Session-learned block on the warp-hint east row ahead of the player."""
    from src.graph.pathfinding import MAP_WARP_HINT_ROWS

    east_row = MAP_WARP_HINT_ROWS.get(gs.map_key, {}).get("east")
    if east_row is None or gs.player.y != east_row:
        return False
    blocked = session_blocked_for_map(state, gs.map_key)
    return any(y == east_row and x > gs.player.x for x, y in blocked)


def _stuck_recovery_target(gs: GameState, state: AgentState) -> tuple[int, int] | None:
    """Exploration frontier when arbitration sees oscillation or repeat blocks.

    On Route 29, pure frontier exploration prefers unvisited *north* tiles while
    the Cherrygrove path needs a *south* detour around the east ledge wall — that
    override caused a stuck_count=0 up/down thrash at (44,8)↔(44,9). Prefer the
    south-corridor / gate waypoint instead of undoing landmark routing.
    """
    from src.graph.exploration import exploration_target
    from src.graph.navigation_resolve import (
        ROUTE_29_EAST_LEDGE_DEAD_END_X,
        ROUTE_29_SOUTH_CORRIDOR,
        _route_29_gate_south_corridor_waypoint,
    )

    stuck_count = state.get("stuck_count", 0)
    history = state.get("short_term_history", [])
    if not navigation_arbitration_active(stuck_count, state):
        return None
    if not (
        _history_oscillates(history, min_cycles=2, max_positions=6)
        or navigation_repeat_detected(history)
        or _east_corridor_blocked_ahead(gs, state)
    ):
        return None

    # Route 30 post-rival: south corridor (y≥45) must climb at x=12, not thrash
    # south back toward Cherrygrove.
    if (
        gs.map_key == MAP_KEY_ROUTE_30
        and state.get("starter_quest_complete")
        and gs.player.y >= 45
    ):
        climb = (12, 48)
        r31 = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_30, {}).get("route_31_gate")
        if gs.player.x < 12 and find_path(
            gs.player.x,
            gs.player.y,
            climb[0],
            climb[1],
            map_key=gs.map_key,
            state=state,
        ):
            return climb
        if r31 is not None and find_path(
            gs.player.x,
            gs.player.y,
            r31[0],
            r31[1],
            map_key=gs.map_key,
            state=state,
        ):
            return r31

    # Route 31 post-rival: always pull toward west gate (Violet), not east thrash.
    if gs.map_key == MAP_KEY_ROUTE_31 and state.get("starter_quest_complete"):
        west_gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_31, {}).get("west_gate")
        if west_gate is not None and find_path(
            gs.player.x,
            gs.player.y,
            west_gate[0],
            west_gate[1],
            map_key=gs.map_key,
            state=state,
        ):
            return west_gate

    if gs.map_key == MAP_KEY_ROUTE_29:
        meta_r29 = gs.raw_metadata or {}
        egg_return_east = bool(
            meta_r29.get("has_mystery_egg") and not meta_r29.get("egg_delivered")
        )
        # Egg-return is east to New Bark — do not pull toward R30 gate / west gap
        # (live bed_egg_to_gym6 flipped target 59,8 → 10,8 → 4,10 mid thrash).
        if egg_return_east:
            east_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("east_exit")
            if east_exit is not None and find_path(
                gs.player.x,
                gs.player.y,
                east_exit[0],
                east_exit[1],
                map_key=gs.map_key,
                state=state,
            ):
                return east_exit
        else:
            gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
            west_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit")
            west_south_gap = (4, 10)
            px, py = gs.player.x, gs.player.y
            if px >= ROUTE_29_EAST_LEDGE_DEAD_END_X and py <= 11:
                if find_path(
                    px, py, ROUTE_29_SOUTH_CORRIDOR[0], ROUTE_29_SOUTH_CORRIDOR[1],
                    map_key=gs.map_key, state=state,
                ):
                    return ROUTE_29_SOUTH_CORRIDOR
            # Near gate: prefer south gap west of x=8 wall (not A* east detour).
            if gate is not None and px <= gate[0] + 3 and py <= gate[1] + 2:
                if px >= 8 and find_path(
                    px, py, west_south_gap[0], west_south_gap[1],
                    map_key=gs.map_key, state=state,
                ):
                    return west_south_gap
                if west_exit is not None and find_path(
                    px, py, west_exit[0], west_exit[1],
                    map_key=gs.map_key, state=state,
                ):
                    return west_exit
            if gate is not None:
                waypoint = _route_29_gate_south_corridor_waypoint(gs, gate, state)
                if waypoint != (px, py):
                    return waypoint
            if west_exit is not None and find_path(
                px, py, west_exit[0], west_exit[1], map_key=gs.map_key, state=state
            ):
                return west_exit

    explore = exploration_target(gs, state)
    if explore and explore != (gs.player.x, gs.player.y):
        return explore
    return None


def navigator_node(state: AgentState) -> AgentState:
    """Navigate with pathfinding and LLM direction pick among candidates."""
    gs = GameState.model_validate(state.get("game_state", {}))
    _tick_post_warp_wait(state)
    map_key = gs.map_key

    relevant_landmarks = _attach_landmark_context(state, gs)
    target = _navigation_target(gs, map_key=map_key, state=state)
    recovery = _stuck_recovery_target(gs, state)
    if recovery is not None:
        target = recovery
    path = find_path(
        gs.player.x,
        gs.player.y,
        target[0],
        target[1],
        map_key=map_key,
        state=state,
    )
    stuck_count = state.get("stuck_count", 0)
    # Route 29 west handoff: temporary session blocks on the only south gap
    # (e.g. (11,9) after a failed step) make A* return empty and thrash L/R.
    # Retry without session overlay only while stuck is low — once stuck is high
    # the blocks are real NPC edges (live (17,4) left forever if we ignore them).
    # R30 northbound: session blocks from failed steps can wipe A* to the climb
    # or detour west into the x1 soft-lock strip (live gym28 (4,12)→left thrash).
    # Prefer the clean grid path whenever it is shorter or the session path is empty.
    if (
        map_key == MAP_KEY_ROUTE_30
        and target
        and target[1] < gs.player.y
        and stuck_count < 12
    ):
        clean = find_path(
            gs.player.x,
            gs.player.y,
            target[0],
            target[1],
            map_key=map_key,
            state=None,
        )
        if clean and (not path or len(clean) + 2 < len(path) or not path):
            path = clean
    if (
        not path
        and stuck_count < 6
        and map_key == MAP_KEY_ROUTE_29
        and target
        in (
            MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit"),
            (4, 10),
        )
    ):
        path = find_path(
            gs.player.x,
            gs.player.y,
            target[0],
            target[1],
            map_key=map_key,
            state=None,
        )
    # R31 westbound: same session-block detour problem after soft-lock reloads.
    if (
        map_key == MAP_KEY_ROUTE_31
        and target
        and target[0] < gs.player.x
        and stuck_count < 12
    ):
        clean = find_path(
            gs.player.x,
            gs.player.y,
            target[0],
            target[1],
            map_key=map_key,
            state=None,
        )
        if clean and (not path or len(clean) + 2 < len(path)):
            path = clean
    candidates = _navigation_candidates(gs, target, path, state)
    candidates = expand_candidates_on_stuck(gs, candidates, state, stuck_count=stuck_count)
    candidates = reorder_candidates_visit_aware(gs, candidates, state)

    door_exit = _players_house_door_exit(gs, state)
    llm_choice = llm_navigate(gs, state, candidates, relevant_landmarks, target=target)
    if navigation_arbitration_active(stuck_count, state) and candidates:
        if llm_choice not in candidates:
            llm_choice = candidates[0]
    action = select_navigation_action(
        door_exit=door_exit,
        path=path,
        llm_choice=llm_choice,
        candidates=candidates,
        stuck_count=stuck_count,
        gs=gs,
        state=state,
        target=target,
    )

    history = list(state.get("short_term_history", []))
    history.append(f"navigate:{action}@{gs.player.x},{gs.player.y}")
    state["short_term_history"] = history[-20:]
    state["last_action"] = f"navigate_{action}"
    state["last_action_result"] = {
        "direction": action,
        "target": target,
        "path_length": len(path),
        "candidates": candidates,
    }
    state["position_before_action"] = gs.position_key
    state["facing_before_action"] = gs.player.facing
    state["next_node"] = "critic"
    return state


def _blocked_stairs_up(
    gs: GameState, state: AgentState | dict[str, Any] | None = None
) -> bool:
    return house_exit.blocked_stairs_up(gs, state)


def _navigation_candidates(
    gs: GameState,
    target: tuple[int, int],
    path: list,
    state: AgentState | None = None,
) -> list[str]:
    """Build direction candidates for pathfinding + LLM selection."""
    state = state or {}
    primary = direction_toward(gs.player.x, gs.player.y, target[0], target[1])
    if primary == "up" and _blocked_stairs_up(gs, state):
        primary = direction_toward(gs.player.x, gs.player.y, PLAYERS_HOUSE_1F_DOOR[0], PLAYERS_HOUSE_1F_DOOR[1])
    cardinals = walkable_cardinal_candidates(gs, state)
    candidates: list[str] = []
    if path:
        for step in path[:3]:
            if step == "up" and (
                _blocked_stairs_up(gs, state)
                or (gs.map_key == MAP_KEY_ELMS_LAB and starter_quest.blocked_lab_exit(gs))
            ):
                continue
            if cardinals and step not in cardinals:
                continue
            candidates.append(step)
    if primary != "a" and primary not in candidates and primary in cardinals:
        candidates.append(primary)
    recovery = outdoor_interact_recovery_active(
        gs, state
    ) or interact_stall_recovery_active(gs, state)
    if not recovery and (
        house_exit.prefer_interact_candidate(gs, state)
        or generic_prefer_interact_candidate(gs, state)
    ):
        candidates.insert(0, "a")
    elif not recovery and (
        house_exit.stuck_interact_fallback(gs, state)
        or generic_stuck_interact_fallback(gs, state)
    ):
        candidates.append("a")
    elif not recovery and at_target_blocked_ahead_interact_eligible(
        gs.map_key,
        gs.player.x,
        gs.player.y,
        target,
        state=state,
    ):
        candidates.append("a")
    meta = gs.raw_metadata or {}
    if (
        not recovery
        and gs.map_key == MAP_KEY_ELMS_LAB
        and meta.get("has_mystery_egg")
        and not meta.get("egg_delivered")
        and (gs.player.x, gs.player.y)
        in starter_quest.ELMS_LAB_DESK_TILES | {(5, 3), (4, 3)}
    ):
        candidates.insert(0, "a")
    if not candidates:
        candidates = cardinals or _direction_candidates(
            gs.player.x, gs.player.y, target[0], target[1]
        )
    return list(dict.fromkeys(candidates))


def _direction_candidates(sx: int, sy: int, tx: int, ty: int) -> list[str]:
    primary = direction_toward(sx, sy, tx, ty)
    if primary != "a":
        return [primary]
    return ["right", "up", "down", "left"]


def _navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: AgentState | None = None,
) -> tuple[int, int]:
    state = state or {}
    return resolve_navigation_target(gs, state, map_key=map_key or gs.map_key)


def battler_node(state: AgentState) -> AgentState:
    """Battle specialist: LLM decision with HP-heuristic fallback."""
    gs = GameState.model_validate(state.get("game_state", {}))
    battle = gs.battle

    action = llm_battle(gs)
    if action is None:
        max_hp = max(1, int(battle.player_active_max_hp or 1))
        hp_frac = float(battle.player_active_hp or 0) / max_hp
        # Flee wilds early: blackout on R30 warps home (24:7) and undoes Cherry progress
        # (live bedroom run: 26:1 → 24:7 after HP drain). Prefer run below 50%.
        if battle.can_run and hp_frac < 0.5:
            action = "run"
        elif battle.can_run and hp_frac < 0.75 and not state.get("starter_quest_complete"):
            # Pre-egg: XP is optional; keep HP for Mr.Pokemon / egg return.
            action = "run"
        else:
            action = "fight"

    state["last_action"] = f"battle_{action}"
    state["last_action_result"] = {"action": action, "phase": battle.phase.value}
    state["next_node"] = "critic"
    return state


def _history_oscillates_nav_interact(
    history: list[str],
    *,
    min_cycles: int = 3,
    max_positions: int = 4,
) -> bool:
    """Detect navigate-then-interact cycles in a small area (stuck-meter evasion)."""
    if len(history) < min_cycles * 2:
        return False
    window = min(len(history), 20)
    entries: list[tuple[str, str]] = []
    for item in history[-window:]:
        if "@" not in item:
            return False
        action, pos = item.split("@", 1)
        entries.append((action.split(":")[0], pos))
    positions = {pos for _, pos in entries}
    if len(positions) == 0 or len(positions) > max_positions:
        return False
    kinds = {kind for kind, _ in entries}
    if kinds != {"navigate", "interact"}:
        return False
    cycles = 0
    idx = 0
    while idx < len(entries):
        nav_count = 0
        while idx < len(entries) and entries[idx][0] == "navigate":
            nav_count += 1
            idx += 1
        interact_count = 0
        while idx < len(entries) and entries[idx][0] == "interact":
            interact_count += 1
            idx += 1
        if nav_count > 0 and interact_count > 0:
            cycles += 1
        elif nav_count > 0:
            break
    return cycles >= min_cycles


def _parse_history_xy(pos: str) -> tuple[int, int] | None:
    """Parse x,y from history payload (supports x,y or map:id:x:y)."""
    parts = pos.split(":")
    if len(parts) >= 2 and parts[-1].lstrip("-").isdigit() and parts[-2].lstrip("-").isdigit():
        try:
            return int(parts[-2]), int(parts[-1])
        except ValueError:
            return None
    if "," in pos:
        a, b = pos.split(",", 1)
        try:
            return int(a), int(b)
        except ValueError:
            return None
    return None


def _history_oscillates_nav_only(
    history: list[str],
    *,
    min_cycles: int = 3,
    max_positions: int = 6,
) -> bool:
    """Detect navigate-only ping-pong across a small tile pocket.

    Two signals (either is enough):
    - Classic: few unique tiles each revisited >= min_cycles times.
    - Bounding-box: many pure-nav steps confined to a small area (covers the
      live Route 29 sign-pocket case where stuck_count stays 0 while the agent
      wanders 5+ tiles without net progress).
    """
    if len(history) < min_cycles * 2:
        return False
    window = min(len(history), 20)
    positions_list: list[str] = []
    coords: list[tuple[int, int]] = []
    for item in history[-window:]:
        if "@" not in item:
            return False
        action, pos = item.split("@", 1)
        if action.split(":")[0] != "navigate":
            return False
        positions_list.append(pos)
        parsed = _parse_history_xy(pos)
        if parsed is not None:
            coords.append(parsed)
    unique = set(positions_list)
    if len(unique) < 2:
        return False
    counts: dict[str, int] = {}
    for pos in positions_list:
        counts[pos] = counts.get(pos, 0) + 1
    if len(unique) <= max_positions and min(counts.values()) >= min_cycles:
        return True
    # Compact pure-nav pocket: enough steps, small bbox, repeated tiles.
    # Live Route 29 sign pocket wanders ~10 tiles twice in a 20-step window
    # (max count=2), so do not require min_cycles per tile.
    min_pocket_steps = max(10, min_cycles * 3)
    if len(coords) < min_pocket_steps or len(coords) != len(positions_list):
        return False
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    if span_x > 6 or span_y > 3:
        return False
    if len(unique) > 12:
        return False
    revisited = sum(1 for n in counts.values() if n >= 2)
    extra_visits = sum(n - 1 for n in counts.values() if n >= 2)
    return (
        max(counts.values()) >= 2
        and revisited >= 2
        and extra_visits >= max(min_cycles, 2)
    )


def _history_oscillates(
    history: list[str],
    *,
    min_cycles: int = 3,
    max_positions: int = 4,
) -> bool:
    """Detect navigation loops: nav+interact cycles or pure nav ping-pong."""
    if _history_oscillates_nav_interact(
        history, min_cycles=min_cycles, max_positions=max_positions
    ):
        return True
    return _history_oscillates_nav_only(
        history, min_cycles=min_cycles, max_positions=max_positions
    )


def _history_interact_repeats(history: list[str], *, min_count: int = 5) -> bool:
    """Detect same-tile interact spam with no navigation progress."""
    if len(history) < min_count:
        return False
    positions: set[str] = set()
    for item in history[-min_count:]:
        if "@" not in item:
            return False
        action, pos = item.split("@", 1)
        if action.split(":")[0] != "interact":
            return False
        positions.add(pos)
    return len(positions) == 1


def critic_node(state: AgentState) -> AgentState:
    """Post-action review: loop detection and risk veto. Always routes through memory."""
    gs = GameState.model_validate(state.get("game_state", {}))
    history = state.get("short_term_history", [])
    stuck = state.get("stuck_count", 0)

    recent = history[-5:] if history else []
    dialog_active = generic_is_interact_needed(gs, state)
    repetition = (
        not dialog_active
        and len(recent) >= 3
        and len(set(recent[-3:])) == 1
        and stuck >= 2
    )
    oscillation = not dialog_active and _history_oscillates(history, min_cycles=3)
    # Outdoor open textbox: keep pure A without critic→planner LLM thrash
    # (live R30 (12,48) spent minutes on replan while dialog still needed A).
    outdoor_open_textbox = gs.in_text_box and gs.map_key not in INDOOR_NAV_STUCK_MAPS
    interact_spam = (
        not outdoor_open_textbox
        and _history_interact_repeats(history, min_count=5)
        and (
            stuck >= 2
            or state.get("interact_no_progress_count", 0)
            >= INTERACT_NO_PROGRESS_RECOVERY
        )
    )

    if repetition or oscillation or interact_spam or stuck >= STUCK_THRESHOLD:
        state["critic_verdict"] = "replan"
        state["critic_notes"] = "Detected loop or high stuck count"
        state["should_replan"] = True
        state["replan_count"] = state.get("replan_count", 0) + 1
        events = list(state.get("replan_events", []))
        events.append(
            {
                "step": state.get("metrics", {}).get("steps", 0),
                "stuck_count": stuck,
                "position": gs.position_key,
                "recovered": False,
            }
        )
        state["replan_events"] = events[-50:]
        _capture_stuck_episode(state, gs)
    elif state.get("last_action", "").startswith("battle_run"):
        state["critic_verdict"] = "caution"
        state["critic_notes"] = "Retreated from battle"
    else:
        state["critic_verdict"] = "proceed"
        state["critic_notes"] = "Action acceptable"

    state["next_node"] = "memory"
    return state


def memory_node(state: AgentState) -> AgentState:
    """Memory manager: milestones, step counter, map tracking."""
    gs = GameState.model_validate(state.get("game_state", {}))
    milestones = list(state.get("milestones", []))
    maps_visited = list(state.get("maps_visited", []))

    discoveries: list[dict[str, Any]] = []
    if gs.map_key not in maps_visited:
        maps_visited.append(gs.map_key)
        discoveries.append(discover_map_visit_landmark(gs))
        if (
            gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
            and not landmark_known(state.get("known_landmarks", []), MR_POKEMONS_HOUSE_ENTRANCE_ID)
        ):
            discoveries.append(discover_mr_pokemon_entrance_landmark(gs))
    state["maps_visited"] = maps_visited

    transition = state.get("last_map_transition") or {}
    if transition.get("to_map"):
        from_map = transition.get("from_map")
        to_map = transition.get("to_map")
        from_pos = transition.get("from_pos") or {}
        known = list(state.get("known_landmarks", [])) + discoveries
        if (
            to_map == MAP_KEY_ELMS_LAB
            and not landmark_known(known, ELMS_LAB_INTERIOR_ID)
        ):
            discoveries.extend(
                discover_elms_lab_landmarks(
                    gs,
                    entrance_map_key=from_pos.get("map_key"),
                    entrance_x=from_pos.get("x"),
                    entrance_y=from_pos.get("y"),
                )
            )
        for landmark in discover_quest_transition_landmarks(
            from_map=from_map,
            to_map=to_map,
            from_pos=from_pos,
        ):
            if not landmark_known(known, str(landmark.get("id"))):
                discoveries.append(landmark)
                known.append(landmark)
        state["last_map_transition"] = {}

    milestone = _check_milestone(gs, state, maps_visited)
    if milestone and milestone not in milestones:
        milestones.append(milestone)
        logger.info("Milestone: %s", milestone)
        if milestone == house_exit.HOUSE_EXIT_MILESTONE:
            house_exit.on_house_exit_complete(state, gs)
        elif milestone == early_progression.MILESTONE_ENTERED_FIRST_GYM:
            early_progression.on_early_progression_complete(state, gs)
        # Rival milestone is recorded only — do not complete starter quest here.
        # Canon order is rival *before* egg delivery; completion requires
        # egg_delivered and a cleared rival scene (see maybe_complete_starter_quest).

    # Complete starter quest when egg is delivered and rival scene is resolved
    # (covers live rival before delivery, and missed in-battle frames after FinishRival).
    if not state.get("starter_quest_complete"):
        starter_quest.maybe_complete_starter_quest(gs, state)

    if milestone == starter_quest.MILESTONE_ENTERED_LAB and not landmark_known(
        state.get("known_landmarks", []), ELMS_LAB_INTERIOR_ID
    ):
        discoveries.extend(discover_elms_lab_landmarks(gs))

    if discoveries:
        _persist_landmark_discoveries(state, discoveries)

    starter_quest.ensure_house_exit_complete(gs, state)
    if starter_quest.in_starter_quest(gs, state):
        starter_quest.sync_subgoals(gs, state)
    elif early_progression.in_early_progression(gs, state):
        early_progression.sync_subgoals(gs, state)
    elif gs.map_key == MAP_KEY_ELMS_LAB and not state.get("starter_quest_complete"):
        # Still in lab pre-complete (starter pick / egg delivery); keep quest subgoals.
        starter_quest.sync_subgoals(gs, state)

    state["milestones"] = milestones
    state["badges_at_last_check"] = gs.total_badges
    metrics = dict(state.get("metrics", {}))
    metrics["steps"] = metrics.get("steps", 0) + 1
    state["metrics"] = metrics
    state["next_node"] = "supervisor"
    return state


def _check_milestone(
    gs: GameState, state: AgentState, maps_visited: list[str]
) -> str | None:
    earned = state.get("milestones", [])
    house = house_exit.house_milestone(gs, maps_visited)
    if house and house not in earned:
        return house
    quest = starter_quest.starter_milestone(gs, maps_visited)
    if quest and quest not in earned:
        return quest
    if gs.map_key == MAP_KEY_ROUTE_29 and maps_visited.count(MAP_KEY_ROUTE_29) == 1:
        return "Reached Route 29"
    progress = early_progression.progression_milestone(gs, maps_visited)
    if progress and progress not in earned:
        return progress
    if gs.battle.in_battle and gs.battle.phase.value == "wild":
        wild_key = "wild_encounter"
        if wild_key not in state.get("milestones", []):
            return "Wild Pokemon encounter"
    badges = gs.total_badges
    if badges > state.get("badges_at_last_check", 0):
        return f"Earned badge (total: {badges})"
    return None


def apply_action_node(state: AgentState, emulator: Any = None) -> AgentState:
    """Execute last_action against emulator and update stuck meter from movement."""
    from src.tools import pokemon_tools

    action = state.get("last_action", "")
    if not action:
        return state

    pos_before = state.get("position_before_action", "")
    if emulator is None:
        if action.startswith("navigate_") and pos_before:
            gs_stub = None
            if state.get("game_state"):
                gs_stub = GameState.model_validate(state["game_state"])
            _update_stuck_from_movement(
                state, action, pos_before, pos_before, gs_stub
            )
        return state
    if not pos_before:
        gs_before = GameState.model_validate(state.get("game_state", {}))
        pos_before = gs_before.position_key

    gs_before = GameState.model_validate(state.get("game_state", {}))
    map_before = gs_before.map_key

    pokemon_tools.bind_emulator(emulator)
    try:
        if action == "wait_script":
            emulator.tick(SCRIPT_WAIT_TICKS)
        elif action == "plan_replan":
            emulator.tick(1)
        elif action in (
            house_exit.HOUSE_EXIT_DONE_ACTION,
            starter_quest.STARTER_QUEST_DONE_ACTION,
            early_progression.EARLY_PROGRESSION_DONE_ACTION,
        ):
            emulator.tick(1)
        elif (
            action.startswith("navigate_")
            or action.startswith("bootstrap_")
            or action.startswith("interact_")
        ):
            direction = action.split("_", 1)[1]
            # navigate_a is a nav-path A press (e.g. at-target ball/door); treat like
            # interact for hold/tick/script-progress so menus and multi-page dialog work.
            is_a_press = direction == "a" and (
                action.startswith("interact_") or action.startswith("navigate_")
            )
            if action.startswith("interact_") or is_a_press:
                gs_pre_interact = GameState.model_validate(state.get("game_state", {}))
                state["pre_action_script_key"] = _script_progress_key(gs_pre_interact)
            if direction in ("up", "down", "left", "right", "a", "b", "start", "select"):
                hold = 12 if direction in ("up", "down", "left", "right") else 8
                if is_a_press:
                    hold = INTERACT_HOLD_FRAMES
                emulator.press_button(direction, hold_frames=hold)  # type: ignore[arg-type]
                if direction in ("up", "down", "left", "right"):
                    # Longer settle when outdoor stuck (NPC collisions / lag).
                    settle = 30
                    if (
                        int(state.get("stuck_count", 0)) >= 3
                        and GameState.model_validate(state.get("game_state", {})).map_key
                        not in INDOOR_NAV_STUCK_MAPS
                    ):
                        settle = 60
                    emulator.tick(settle)
                elif direction == "b":
                    # Longer settle after B when outdoor soft-lock (menu/dialog cancel).
                    b_settle = 40 if int(state.get("stuck_count", 0)) >= 8 else 20
                    emulator.tick(b_settle)
                elif action.startswith("interact_") or is_a_press:
                    gs_tick = GameState.model_validate(state.get("game_state", {}))
                    emulator.tick(_interact_tick_frames(gs_tick))
        elif action.startswith("battle_"):
            battle_action = action.replace("battle_", "")
            pokemon_tools.battle_decide.invoke({"action": battle_action})
        gs = emulator.get_game_state()
        state = update_game_state(state, gs)
        if not state.get("bootstrap_complete") and (gs.raw_metadata or {}).get(
            "movement_ready"
        ):
            state["bootstrap_complete"] = True
            state["phase"] = "explore"
            state["stuck_count"] = 0
        if map_before != gs.map_key:
            parsed = parse_position_key(pos_before)
            if parsed is not None:
                from_map, from_x, from_y = parsed
                state["last_map_transition"] = {
                    "from_map": from_map,
                    "from_pos": {"map_key": from_map, "x": from_x, "y": from_y},
                    "to_map": gs.map_key,
                    "to_pos": {"x": gs.player.x, "y": gs.player.y},
                }
            if action.startswith("navigate_"):
                state["stuck_count"] = 0
                clear_pocket_stuck(state)
        house_exit.on_map_change(map_before, gs, state, action=action)
        starter_quest.on_map_change(map_before, gs, state, action=action)
        if action.startswith("bootstrap_"):
            from src.emulator.bootstrap import (
                BootstrapResult,
                apply_bootstrap_metadata,
                is_bootstrap_done,
            )

            if pos_before and gs.position_key != pos_before:
                state["movement_observed"] = True
            if is_bootstrap_done(emulator, gs, state):
                gs = apply_bootstrap_metadata(
                    gs,
                    BootstrapResult(
                        success=True,
                        movement_ready=True,
                        map_loaded=True,
                        actions_taken=state.get("bootstrap_action_index", 0),
                        frames_elapsed=0,
                    ),
                )
                state = update_game_state(state, gs)
                state["bootstrap_complete"] = True
                state["phase"] = "explore"
                state["stuck_count"] = 0
            else:
                state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        elif action.startswith("interact_") or (
            action.startswith("navigate_") and action.endswith("_a")
        ):
            _update_stuck_from_interaction(state, action, pos_before, gs)
        else:
            _update_stuck_from_movement(
                state,
                action,
                pos_before,
                gs.position_key,
                gs,
            )
    except Exception as exc:
        state["error"] = str(exc)
        logger.error("Action execution failed: %s", exc)

    return state


def _update_stuck_from_movement(
    state: AgentState,
    action: str,
    pos_before: str,
    pos_after: str,
    gs: GameState | None = None,
) -> None:
    """Increment stuck only when a navigation action fails to change position."""
    if not action.startswith("navigate_"):
        return
    if action.endswith("_a"):
        # Outdoor soft-lock recovery presses navigate_a while still stuck on the
        # same tile. Decrementing stuck here reset the meter every A press so
        # recovery never escalated (live (35,4) stuck frozen at 14 with A spam).
        # Only ease stuck when A is a justified interact press at a nav target.
        if pos_before != pos_after:
            state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        elif int(state.get("stuck_count", 0)) < 8:
            state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        # else: leave stuck_count alone so outdoor A/B recovery can keep climbing
        return
    if action.endswith("_b"):
        # B recovery: position change eases stuck; same-tile B still counts as stuck.
        if pos_before != pos_after:
            state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        else:
            state["stuck_count"] = state.get("stuck_count", 0) + 1
        return
    moved = pos_before != pos_after
    if moved:
        if gs is not None:
            parsed = parse_position_key(pos_after)
            if parsed is not None:
                map_key, x, y = parsed
                state["recent_nav_positions"] = append_nav_position(
                    state.get("recent_nav_positions"),
                    map_key,
                    x,
                    y,
                )
                thrash = nav_thrash_severity(
                    state.get("recent_nav_positions") or [],
                    window=12,
                )
                # Pure-nav thrash changes position so legacy stuck-- left meter at 0
                # (live R29 11,10↔11,11; R30 7↔8,30; 26:2↔26:1 bounce). Bump stuck
                # so M3/M11 arbitration and outdoor recovery engage.
                if thrash >= 1:
                    state["stuck_count"] = int(state.get("stuck_count", 0)) + thrash
                    record_session_walkable(state, map_key, x, y)
                    if in_navigation_pocket(state, x, y):
                        record_pocket_nav_failure(state, x, y)
                    _mark_replan_recovery(state, gs, pos_before, pos_after)
                    return
                if in_navigation_pocket(state, x, y):
                    record_session_walkable(state, gs.map_key, x, y)
                    _mark_replan_recovery(state, gs, pos_before, pos_after)
                    return
        clear_pocket_stuck(state)
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        state["interact_no_progress_count"] = 0
        state["interact_stall_escape_fails"] = 0
        clear_interact_stall_escape(state)
        if gs is not None:
            parsed = parse_position_key(pos_after)
            if parsed is not None:
                map_key, x, y = parsed
                record_session_walkable(state, map_key, x, y)
                if map_key == MAP_KEY_ROUTE_29 and (x, y) == ROUTE_29_Y11_DEAD_END:
                    record_session_blocked(state, map_key, x, y)
            _mark_replan_recovery(state, gs, pos_before, pos_after)
        return
    # Failed move while stall-escape is latched: player may still be script-locked
    # (e.g. post-Mom EVENT flag set but dialog/movement hold remains). After a few
    # failures, drop the latch so interactor can finish remaining dialog.
    #
    # Do NOT mark the failed neighbor as session-blocked while escaping: live Route
    # 29 dialog residue makes left/up "fail" without a real wall, and false blocks
    # disconnect A* (e.g. (19,4) only exits west through (18,4)).
    #
    # Same for outdoor open-dialog / sticky-script nav fails: every cardinal can
    # "fail" without a real wall (live (40,14) left+down thrash after NPC talk).
    escaping = bool(state.get("interact_stall_escape"))
    if escaping:
        fails = int(state.get("interact_stall_escape_fails", 0)) + 1
        state["interact_stall_escape_fails"] = fails
        if fails >= 3:
            clear_interact_stall_escape(state)
            state["interact_stall_escape_fails"] = 0
            state["interact_no_progress_count"] = 0
    outdoor_dialog_residue = False
    prior_stuck = int(state.get("stuck_count", 0))
    if gs is not None:
        meta = gs.raw_metadata or {}
        # Early dialog residue must not false-block A* neighbors. After sustained
        # stuck (live (18,4) left forever), treat fails as real walls so path can
        # detour around NPCs that sit on the only west tile.
        outdoor_dialog_residue = (
            gs.map_key not in INDOOR_NAV_STUCK_MAPS
            and prior_stuck < 6
            and bool(
                gs.in_text_box
                or meta.get("in_script")
                or meta.get("script_active")
                or state.get("interact_stall_escape")
            )
        )
    state["stuck_count"] = prior_stuck + 1
    if gs is not None and not escaping and not outdoor_dialog_residue:
        parsed_before = parse_position_key(pos_before)
        if parsed_before is not None:
            map_key, x, y = parsed_before
            if map_key == gs.map_key:
                record_pocket_nav_failure(state, x, y)
                direction = action.removeprefix("navigate_")
                delta = _DIRECTION_DELTA.get(direction)
                if delta is not None:
                    dx, dy = delta
                    nx, ny = x + dx, y + dy
                    west_row = MAP_WARP_HINT_ROWS.get(map_key, {}).get("west")
                    west_edge = MAP_LANDMARK_ANCHORS.get(map_key, {}).get("west_exit")
                    skip_oob_edge = (
                        west_row is not None
                        and west_edge is not None
                        and y == west_row
                        and direction == "left"
                        and nx <= west_edge[0]
                    )
                    if not skip_oob_edge:
                        record_session_blocked(state, map_key, nx, ny)


def _mark_replan_recovery(
    state: AgentState,
    gs: GameState,
    pos_before: str,
    pos_after: str,
) -> None:
    events = list(state.get("replan_events", []))
    if not events or events[-1].get("recovered"):
        return
    last = events[-1]
    if pos_before != pos_after or state.get("stuck_count", 0) < last.get("stuck_count", 0):
        last = {**last, "recovered": True}
        events[-1] = last
        state["replan_events"] = events


def _script_progress_key(gs: GameState) -> tuple[Any, ...]:
    meta = gs.raw_metadata or {}
    return (
        meta.get("script_pos"),
        gs.in_text_box,
        meta.get("script_mode"),
        gs.battle.in_battle,
        bool(meta.get("in_script")),
        bool(meta.get("script_active")),
    )


def _meaningful_script_progress(
    pre_key: tuple[Any, ...] | None, post_key: tuple[Any, ...]
) -> bool:
    """True when dialog/script state advanced between pre/post action snapshots.

    Includes ``script_pos`` changes: multi-page SCRIPT_READ (notably post-Mom
    MeetMom follow-up) often advances only the script pointer while in_text_box,
    script_mode, and in_battle stay constant. Ignoring pos-only changes caused
    INTERACT_STALL_STREAK to arm mid-dialog and thrash with navigate at (9,1).

    Compares the shared prefix so legacy 4-tuples vs extended 6-tuples do not
    spuriously count as progress when only the key length differs.
    """
    if pre_key is None:
        return False
    if pre_key == post_key:
        return False
    n = min(len(pre_key), len(post_key))
    if n == 0:
        return False
    return pre_key[:n] != post_key[:n]


def _update_stuck_from_interaction(
    state: AgentState,
    action: str,
    pos_before: str,
    gs: GameState,
) -> None:
    """Dialog interactions advance story without map movement.

    Live multi-page dialog (open textbox) may freeze the script progress key for
    stretches; short freezes must not inflate ``stuck_count`` like a failed move.
    ``interact_no_progress_count`` still accumulates so long residue recovery can
    arm. MeetMom pending additionally zeros counters because movement is hard-
    locked until the event flag (safety; not the only multi-page protection).
    """
    del action
    meta = gs.raw_metadata or {}
    pre_key = state.pop("pre_action_script_key", None)
    post_key = _script_progress_key(gs)
    script_progressed = _meaningful_script_progress(pre_key, post_key)
    if house_exit.mom_scene_pending(gs):
        # MeetMom is pure A until the event flag. Movement is locked at entry;
        # zero counters so a high count cannot fire recovery the instant the
        # flag flips while remaining dialog still needs A. Open-textbox grace
        # (below) is the generic multi-page protection for other scenes.
        state["phase"] = "explore"
        state["stuck_count"] = 0
        state["interact_no_progress_count"] = 0
        clear_interact_stall_escape(state)
        return
    if pos_before != gs.position_key:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 2)
        state["interact_no_progress_count"] = 0
        state["outdoor_script_frozen_count"] = 0
        clear_interact_stall_escape(state)
        _mark_replan_recovery(state, gs, pos_before, gs.position_key)
    elif (
        gs.map_key not in INDOOR_NAV_STUCK_MAPS
        and pos_before == gs.position_key
    ):
        # Same-tile outdoor interact (any ROM interact signal): always climb
        # no_progress/freeze so supervisor can break out even when script_pos
        # jitters or textbox flags flicker (live bed_chain_gym13 (18,15) stuck=0).
        state["interact_no_progress_count"] = (
            int(state.get("interact_no_progress_count", 0)) + 1
        )
        state["outdoor_script_frozen_count"] = (
            int(state.get("outdoor_script_frozen_count", 0)) + 1
        )
        parsed = parse_position_key(gs.position_key)
        if parsed is not None:
            mk, px, py = parsed
            state["recent_nav_positions"] = append_nav_position(
                state.get("recent_nav_positions"), mk, px, py
            )
        frozen_n = int(state["outdoor_script_frozen_count"])
        if gs.in_text_box:
            # Open outdoor textbox: climb stuck after short multi-page grace.
            if frozen_n >= 6:
                state["stuck_count"] = int(state.get("stuck_count", 0)) + 1
        else:
            # Closed textbox residue (sticky script) or false interact pin:
            # stuck++ and session-block so navigator leaves the tile.
            state["stuck_count"] = int(state.get("stuck_count", 0)) + 1
            if parsed is not None:
                record_session_blocked(state, mk, px, py)
            # Dialog just closed (pre open → post closed): clear no_progress so
            # the next nav step is not treated as continuing thrash.
            if pre_key is not None and bool(pre_key[1]) and not gs.in_text_box:
                state["interact_no_progress_count"] = 0
                state["outdoor_script_frozen_count"] = 0
    elif script_progressed:
        # Outdoor multi-page SCRIPT_READ often jitters script_pos while the
        # textbox stays open (live R30/R31 soft-lock tiles). Treating that as
        # progress zeroed outdoor_script_frozen_count forever so rare-B never
        # fired and stuck stayed 0 through 200+ interact_a steps. Only clear
        # outdoor freeze when the textbox actually closes or we leave script.
        outdoor_open = (
            gs.in_text_box
            and gs.map_key not in INDOOR_NAV_STUCK_MAPS
            and pre_key is not None
            and bool(pre_key[1])  # was in textbox
        )
        if outdoor_open:
            state["interact_no_progress_count"] = (
                state.get("interact_no_progress_count", 0) + 1
            )
            state["outdoor_script_frozen_count"] = (
                int(state.get("outdoor_script_frozen_count", 0)) + 1
            )
            if int(state["outdoor_script_frozen_count"]) >= 12:
                state["stuck_count"] = int(state.get("stuck_count", 0)) + 1
        else:
            state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
            state["interact_no_progress_count"] = 0
            state["outdoor_script_frozen_count"] = 0
            clear_interact_stall_escape(state)
            if (
                pre_key is not None
                and pre_key[1]
                and not gs.in_text_box
                and gs.map_key not in INDOOR_NAV_STUCK_MAPS
            ):
                parsed = parse_position_key(gs.position_key)
                if parsed is not None:
                    map_key, x, y = parsed
                    record_session_blocked(state, map_key, x, y)
    elif gs.in_text_box or bool(meta.get("in_script")):
        # No meaningful progress (keys frozen, including script_pos).
        # Missing pre_key keeps legacy soft-progress (stuck--) for unit fixtures.
        if pre_key is not None and not script_progressed:
            state["interact_no_progress_count"] = (
                state.get("interact_no_progress_count", 0) + 1
            )
            no_progress = int(state["interact_no_progress_count"])
            # Indoor open textbox: never stuck++ / nav-escape (story multi-page).
            # Outdoor open textbox: track no_progress; only arm after long recovery
            # so multi-page NPC/sign dialog can finish with A.
            indoor_live_dialog = (
                gs.in_text_box and gs.map_key in INDOOR_NAV_STUCK_MAPS
            )
            outdoor_live_dialog = gs.in_text_box and not indoor_live_dialog
            if indoor_live_dialog:
                if state.get("interact_stall_escape"):
                    clear_interact_stall_escape(state)
            elif outdoor_live_dialog:
                # Track frozen count for diagnostics, but never arm nav-escape
                # while the outdoor textbox is still open (B/nav soft-locks
                # SCRIPT_READ — live R30). Keep pure A until the box closes.
                state["outdoor_script_frozen_count"] = (
                    int(state.get("outdoor_script_frozen_count", 0)) + 1
                )
                frozen_n = int(state["outdoor_script_frozen_count"])
                # Record same-tile samples so nav_thrash_severity sees freezes.
                parsed = parse_position_key(gs.position_key)
                if parsed is not None:
                    mk, px, py = parsed
                    state["recent_nav_positions"] = append_nav_position(
                        state.get("recent_nav_positions"), mk, px, py
                    )
                # Climb stuck earlier (was 40): live bed_chain_gym2 sat on
                # interact_a at (10,19) with stuck frozen at 5 for 300+ steps.
                if frozen_n >= 12:
                    state["stuck_count"] = int(state.get("stuck_count", 0)) + 1
                # Do not arm_interact_stall_escape while textbox open.
            else:
                state["stuck_count"] = state.get("stuck_count", 0) + 1
                if should_arm_interact_stall(gs, no_progress):
                    arm_interact_stall_escape(state)
                parsed = parse_position_key(gs.position_key)
                if parsed is not None:
                    map_key, x, y = parsed
                    record_session_blocked(state, map_key, x, y)
        else:
            state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
    else:
        state["stuck_count"] = state.get("stuck_count", 0) + 1
        state["interact_no_progress_count"] = (
            state.get("interact_no_progress_count", 0) + 1
        )
        if should_arm_interact_stall(gs, state["interact_no_progress_count"]):
            arm_interact_stall_escape(state)
