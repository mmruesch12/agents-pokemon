"""Frontier exploration when landmark targets are unknown."""
from __future__ import annotations

import heapq
from typing import Any

from src.graph.pathfinding import MAP_GRIDS, MAP_WARP_HINT_ROWS, _is_walkable, find_path
from src.state.models import GameState


def exploration_hint_text(state: dict[str, Any], gs: GameState) -> str:
    hints = [str(state.get("active_subgoal", "")), *state.get("subgoals", []), *state.get("current_plan", [])]
    if state.get("house_exit_complete"):
        from src.graph.phases import starter_quest
        quest = starter_quest.decompose_subgoals(gs)
        if quest:
            hints.extend(quest)
    return " ".join(hints)


def exploration_hint_tile(state: dict[str, Any], gs: GameState):
    if not state.get("house_exit_complete"):
        return None
    from src.graph.phases import starter_quest
    from src.memory.landmarks import ELMS_LAB_ENTRANCE_ID, landmark_known

    if not starter_quest.in_starter_quest(gs, state):
        return None
    text = exploration_hint_text(state, gs).lower()
    landmarks = list(state.get("known_landmarks", []))
    meta = gs.raw_metadata or {}
    if (
        gs.map_key == "24:4"
        and not landmark_known(landmarks, ELMS_LAB_ENTRANCE_ID)
        and not meta.get("has_starter")
    ):
        if "lab" in text or "elm" in text or "starter" in text:
            return starter_quest.NEW_BARK_LAB_WARP
    return None


def _subgoal_exploration_bias(text: str):
    text = text.lower()
    if "lab" in text or "elm" in text:
        return (0, 0)
    return None


def _landmark_axis_fallback(
    gs: GameState,
    state: dict[str, Any],
    landmark_id: str,
) -> tuple[int, int]:
    from src.memory.landmarks import NEW_BARK_EAST_EXIT_ID, ROUTE_29_NORTH_GATE_ID, ROUTE_30_NORTH_GATE_ID

    if landmark_id == NEW_BARK_EAST_EXIT_ID:
        return _frontier_exploration_target(gs, state, axis="east")
    if landmark_id in (ROUTE_29_NORTH_GATE_ID, ROUTE_30_NORTH_GATE_ID):
        return _frontier_exploration_target(gs, state, axis="north")
    return (gs.player.x + 1, gs.player.y)


def _frontier_exploration_target(
    gs: GameState,
    state: dict[str, Any],
    *,
    axis: str,
) -> tuple[int, int]:
    """Pick a reachable frontier tile along an axis using the walkable grid."""
    del state
    grid = MAP_GRIDS.get(gs.map_key)
    px, py = gs.player.x, gs.player.y
    if grid is None:
        if axis == "east":
            return (px + 1, py)
        return (px, max(0, py - 1))
    reachable: list[tuple[int, int]] = []
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell != 0 or (x, y) == (px, py):
                continue
            if find_path(px, py, x, y, map_key=gs.map_key):
                reachable.append((x, y))
    if not reachable:
        if axis == "east":
            return (px + 1, py)
        return (px, max(0, py - 1))

    warp_hints = MAP_WARP_HINT_ROWS.get(gs.map_key, {})
    if axis == "east":
        gate_row = warp_hints.get("east")
        if gate_row is not None:
            max_x = max(t[0] for t in reachable)
            gate_tiles = [t for t in reachable if t[0] == max_x and t[1] == gate_row]
            if gate_tiles:
                return gate_tiles[0]
        max_x = max(t[0] for t in reachable)
        eastern = [t for t in reachable if t[0] == max_x]
        return min(eastern, key=lambda tile: tile[1])

    gate_row = warp_hints.get("north")
    if gate_row is not None:
        gate_tiles = [t for t in reachable if t[1] == gate_row]
        if gate_tiles:
            return min(gate_tiles, key=lambda tile: abs(tile[0] - px))
    return min(reachable, key=lambda tile: (tile[1], abs(tile[0] - px)))


def retired_geography_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    """Landmark id for retired phase geography on the current map, if applicable."""
    from src.state.gold_state_reader import (
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
    )
    from src.memory.landmarks import (
        NEW_BARK_EAST_EXIT_ID,
        ROUTE_29_NORTH_GATE_ID,
        ROUTE_30_NORTH_GATE_ID,
    )

    meta = gs.raw_metadata or {}
    has_starter = bool(meta.get("has_starter"))
    has_egg = bool(meta.get("has_mystery_egg"))
    if not state.get("house_exit_complete") or not has_starter or has_egg:
        return None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        return NEW_BARK_EAST_EXIT_ID
    if gs.map_key == MAP_KEY_ROUTE_29:
        return ROUTE_29_NORTH_GATE_ID
    if gs.map_key == MAP_KEY_ROUTE_30:
        return ROUTE_30_NORTH_GATE_ID
    return None


def retired_geography_target(gs: GameState, state: dict[str, Any] | None = None) -> tuple[int, int] | None:
    """Resolve retired quest geography via landmarks or exploration fallbacks."""
    from src.memory.landmarks import find_landmark, landmark_coords, landmark_known

    state = state or {}
    landmark_id = retired_geography_landmark_id(gs, state)
    if landmark_id is None:
        return None
    landmarks = list(state.get("known_landmarks", []))
    if landmark_known(landmarks, landmark_id):
        landmark = find_landmark(landmarks, landmark_id=landmark_id)
        if landmark is not None and landmark.get("map_key") == gs.map_key:
            return landmark_coords(landmark)
        return _landmark_axis_fallback(gs, state, landmark_id)
    from src.memory.landmarks import NEW_BARK_EAST_EXIT_ID

    if landmark_id == NEW_BARK_EAST_EXIT_ID:
        return _frontier_exploration_target(gs, state, axis="east")
    return _frontier_exploration_target(gs, state, axis="north")


def exploration_target(gs: GameState, state: dict[str, Any] | None = None, *, hint_tile=None):
    state = state or {}
    hint_tile = hint_tile or exploration_hint_tile(state, gs)
    if hint_tile is None:
        retired = retired_geography_target(gs, state)
        if retired is not None:
            return retired
    if hint_tile is not None:
        path = find_path(gs.player.x, gs.player.y, hint_tile[0], hint_tile[1], map_key=gs.map_key)
        if path or (gs.player.x, gs.player.y) != hint_tile:
            return hint_tile
    visited = {k for k in state.get("visited_positions", []) if k.startswith(f"{gs.map_key}:")}
    grid = MAP_GRIDS.get(gs.map_key)
    bias = _subgoal_exploration_bias(exploration_hint_text(state, gs))
    start = (gs.player.x, gs.player.y)
    open_set = [(0, gs.player.x, gs.player.y, 0)]
    visited_search = {start}
    best_unvisited, best_score = None, float("-inf")
    while open_set:
        _, x, y, dist = heapq.heappop(open_set)
        pos_key = f"{gs.map_key}:{x}:{y}"
        if pos_key not in visited and (x, y) != start:
            score = -(abs(bias[0] - x) + abs(bias[1] - y) + dist * 0.01) if bias else dist
            if score > best_score:
                best_score, best_unvisited = score, (x, y)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited_search or not _is_walkable(grid, nx, ny):
                continue
            visited_search.add((nx, ny))
            heapq.heappush(open_set, (dist + 1, nx, ny, dist + 1))
    return best_unvisited if best_unvisited else (gs.player.x + 1, gs.player.y)


def gated_phase_target(gs, phase_target, *, state=None, landmark_id=None):
    from src.memory.landmarks import find_landmark, landmark_coords

    state = state or {}
    landmarks = list(state.get("known_landmarks", []))
    if landmark_id:
        landmark = find_landmark(landmarks, landmark_id=landmark_id)
        if landmark is not None and landmark.get("map_key") == gs.map_key:
            return landmark_coords(landmark)
        return _landmark_axis_fallback(gs, state, landmark_id)
    return phase_target