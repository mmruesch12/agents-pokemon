"""Frontier exploration when landmark targets are unknown."""
from __future__ import annotations

import heapq
from typing import Any

from src.graph.pathfinding import (
    MAP_GRIDS,
    MAP_LANDMARK_ANCHORS,
    MAP_WARP_HINT_ROWS,
    _is_walkable,
    find_path,
    session_blocked_for_map,
    session_walkable_for_map,
)
from src.state.gold_state_reader import MAP_KEY_NEW_BARK_TOWN, MAP_KEY_ROUTE_29
from src.state.models import GameState

_ROUTE_29_EXIT_MARKERS = (
    "enter route 29",
    "cross route 29",
    "route 29",
)


def exploration_hint_text(state: dict[str, Any], gs: GameState) -> str:
    hints = [str(state.get("active_subgoal", "")), *state.get("subgoals", []), *state.get("current_plan", [])]
    if state.get("starter_quest_complete"):
        from src.graph.phases import early_progression
        progress = early_progression.decompose_subgoals(gs)
        if progress:
            hints.extend(progress)
    elif state.get("house_exit_complete"):
        from src.graph.phases import starter_quest
        quest = starter_quest.decompose_subgoals(gs)
        if quest:
            hints.extend(quest)
    return " ".join(hints)


_WESTBOUND_MARKERS = (
    "travel west",
    "cherrygrove",
    "reach cherrygrove",
    "cross route 29",
    "enter route 29",
)


def exploration_heading_west(
    gs: GameState,
    state: dict[str, Any],
    *,
    hint_tile: tuple[int, int] | None = None,
) -> bool:
    """True when quest hints or position imply westward progress toward Route 29."""
    if hint_tile is not None and hint_tile[0] < gs.player.x:
        return True
    text = exploration_hint_text(state, gs).lower()
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN and any(
        marker in text for marker in _ROUTE_29_EXIT_MARKERS
    ):
        return True
    if gs.map_key == MAP_KEY_ROUTE_29 and any(
        marker in text for marker in _WESTBOUND_MARKERS
    ):
        return True
    west_row = MAP_WARP_HINT_ROWS.get(gs.map_key, {}).get("west")
    west_anchor = MAP_LANDMARK_ANCHORS.get(gs.map_key, {}).get("west_exit")
    if west_row is not None and west_anchor and gs.player.y == west_row:
        # Include standing on the west_exit tile so map_edge_exit can step left.
        return gs.player.x >= west_anchor[0]
    # East-entry y (R29 east_exit is y=8) while targeting west_exit (y=7): still westbound.
    if west_anchor is not None and gs.player.x > west_anchor[0]:
        east_exit = MAP_LANDMARK_ANCHORS.get(gs.map_key, {}).get("east_exit")
        if east_exit is not None and abs(gs.player.y - east_exit[1]) <= 1:
            return True
    return False


def exploration_heading_route_30_gate(
    gs: GameState,
    state: dict[str, Any],
    *,
    hint_tile: tuple[int, int] | None = None,
) -> bool:
    """True when post-starter Route 29 progress should bias toward the north gate."""
    if hint_tile is not None:
        gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
        if gate and hint_tile == gate:
            return True
        if hint_tile[1] < gs.player.y or hint_tile[0] < gs.player.x:
            return True
    if gs.map_key != MAP_KEY_ROUTE_29:
        return False
    text = exploration_hint_text(state, gs).lower()
    # Match early_progression ("Travel west on Route 29") and starter-quest
    # ("Cross Route 29") plus Mr. Pokemon / Cherrygrove corridor language.
    west_markers = (
        "cross route 29",
        "travel west",
        "route 29",
        "cherrygrove",
        "visit mr",
        "mr. pokemon",
        "mr pokemon",
    )
    if not any(marker in text for marker in west_markers):
        return False
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    if not gate:
        return False
    return gs.player.y > gate[1] or gs.player.x > gate[0]


def exploration_hint_tile(state: dict[str, Any], gs: GameState):
    """Return coords only when a known landmark matches the current map."""
    from src.graph.navigation_resolve import _starter_quest_landmark_id
    from src.memory.landmarks import find_landmark, landmark_coords

    landmark_id = _starter_quest_landmark_id(gs, state)
    if landmark_id is None:
        return None
    landmark = find_landmark(list(state.get("known_landmarks", [])), landmark_id=landmark_id)
    if landmark is None or landmark.get("map_key") != gs.map_key:
        return None
    return landmark_coords(landmark)


def exploration_target(
    gs: GameState,
    state: dict[str, Any] | None = None,
    *,
    hint_tile=None,
):
    state = state or {}
    hint_tile = hint_tile or exploration_hint_tile(state, gs)
    if hint_tile is not None:
        path = find_path(
            gs.player.x,
            gs.player.y,
            hint_tile[0],
            hint_tile[1],
            map_key=gs.map_key,
            state=state,
        )
        if path:
            return hint_tile
        if (gs.player.x, gs.player.y) == hint_tile:
            return hint_tile
    visited = {k for k in state.get("visited_positions", []) if k.startswith(f"{gs.map_key}:")}
    grid = MAP_GRIDS.get(gs.map_key)
    start = (gs.player.x, gs.player.y)
    open_set = [(0, gs.player.x, gs.player.y, 0)]
    visited_search = {start}
    best_unvisited, best_score = None, float("-inf")
    west_row = MAP_WARP_HINT_ROWS.get(gs.map_key, {}).get("west")
    north_row = MAP_WARP_HINT_ROWS.get(gs.map_key, {}).get("north")
    hint_west = exploration_heading_west(gs, state, hint_tile=hint_tile)
    hint_gate = exploration_heading_route_30_gate(gs, state, hint_tile=hint_tile)
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    west_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit")
    # East ledge wall (x≥44, y≤11): south detour first; north bias causes thrash.
    east_ledge_detour = (
        gs.map_key == MAP_KEY_ROUTE_29
        and hint_gate
        and gs.player.x >= 40
        and gs.player.y <= 11
    )
    while open_set:
        _, x, y, dist = heapq.heappop(open_set)
        pos_key = f"{gs.map_key}:{x}:{y}"
        if pos_key not in visited and (x, y) != start:
            score = float(dist)
            if hint_west and west_row is not None:
                if y == west_row and x < gs.player.x:
                    score += 10.0 + (gs.player.x - x)
                elif y == west_row:
                    score += 4.0
            if hint_gate and gate is not None:
                if east_ledge_detour:
                    # Prefer south corridor (y≥14) then west — not north pocket tiles.
                    if y > gs.player.y:
                        score += 8.0 + (y - gs.player.y)
                    if y >= 14 and x < gs.player.x:
                        score += 12.0 + (gs.player.x - x) * 0.5
                    if y < gs.player.y:
                        score -= 6.0
                else:
                    if y < gs.player.y:
                        score += 6.0 + (gs.player.y - y)
                    if x < gs.player.x:
                        score += 4.0 + (gs.player.x - x) * 0.5
                    if north_row is not None and y == north_row and y < gs.player.y:
                        score += 8.0
            if score > best_score:
                best_score, best_unvisited = score, (x, y)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            session_walkable = session_walkable_for_map(state, gs.map_key)
            session_blocked = session_blocked_for_map(state, gs.map_key)
            if (nx, ny) in visited_search or not _is_walkable(
                grid,
                nx,
                ny,
                session_walkable=session_walkable,
                session_blocked=session_blocked,
            ):
                continue
            visited_search.add((nx, ny))
            heapq.heappush(open_set, (dist + 1, nx, ny, dist + 1))
    if best_unvisited:
        return best_unvisited
    if east_ledge_detour:
        south = (14, 14)
        if find_path(
            gs.player.x,
            gs.player.y,
            south[0],
            south[1],
            map_key=gs.map_key,
            state=state,
        ):
            return south
        if west_exit is not None and find_path(
            gs.player.x,
            gs.player.y,
            west_exit[0],
            west_exit[1],
            map_key=gs.map_key,
            state=state,
        ):
            return west_exit
    if hint_gate and gate is not None:
        gate_x, gate_y = gate
        if east_ledge_detour:
            return (gs.player.x, min(gs.player.y + 1, 14))
        if gs.player.y > gate_y:
            return (gs.player.x, max(0, gs.player.y - 1))
        if gs.player.x > gate_x:
            return (max(0, gs.player.x - 1), gs.player.y)
    if hint_west and west_row is not None:
        return (max(0, gs.player.x - 1), west_row)
    return (gs.player.x + 1, gs.player.y)


def gated_phase_target(gs, phase_target, *, state=None, landmark_id=None):
    from src.memory.landmarks import find_landmark, landmark_coords

    state = state or {}
    landmarks = list(state.get("known_landmarks", []))
    if landmark_id:
        landmark = find_landmark(landmarks, landmark_id=landmark_id)
        if landmark is not None and landmark.get("map_key") == gs.map_key:
            return landmark_coords(landmark)
        return exploration_target(gs, state)
    return phase_target