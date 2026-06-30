"""Pure resolver for retired starter-quest geography (landmarks + grid fallbacks)."""

from __future__ import annotations

from typing import Any

from src.graph.pathfinding import MAP_GRIDS, MAP_WARP_HINT_ROWS, find_path
from src.state.gold_state_reader import (
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
)
from src.state.models import GameState


def retired_geography_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    """Landmark id for retired phase geography on the current map, if applicable."""
    from src.memory.landmarks import (
        NEW_BARK_EAST_EXIT_ID,
        ROUTE_29_NORTH_GATE_ID,
        ROUTE_30_NORTH_GATE_ID,
    )

    from src.graph.phases import starter_quest

    has_starter = starter_quest.has_starter(gs)
    if not state.get("house_exit_complete") or not has_starter:
        return None
    if state.get("starter_quest_complete"):
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return NEW_BARK_EAST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_29:
            return ROUTE_29_NORTH_GATE_ID
        if gs.map_key == MAP_KEY_ROUTE_30:
            return ROUTE_30_NORTH_GATE_ID
        return None
    has_egg = bool((gs.raw_metadata or {}).get("has_mystery_egg"))
    if has_egg:
        return None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        return NEW_BARK_EAST_EXIT_ID
    if gs.map_key == MAP_KEY_ROUTE_29:
        return ROUTE_29_NORTH_GATE_ID
    if gs.map_key == MAP_KEY_ROUTE_30:
        return ROUTE_30_NORTH_GATE_ID
    return None


def _frontier_exploration_target(
    gs: GameState,
    *,
    axis: str,
) -> tuple[int, int]:
    """Pick a reachable frontier tile along an axis using the walkable grid."""
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


def _frontier_for_landmark_id(landmark_id: str) -> str:
    from src.memory.landmarks import NEW_BARK_EAST_EXIT_ID

    if landmark_id == NEW_BARK_EAST_EXIT_ID:
        return "east"
    return "north"


def resolve_egg_return_geography(
    gs: GameState, state: dict[str, Any] | None = None
) -> tuple[int, int] | None:
    """Return-leg targets after Mystery Egg is obtained."""
    from src.graph.phases import starter_quest
    from src.state.gold_state_reader import (
        MAP_KEY_MR_POKEMONS_HOUSE,
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
    )

    state = state or {}
    if not starter_quest._has_egg(gs) or starter_quest._egg_delivered(gs):
        return None
    if gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE:
        return (5, 8)
    if gs.map_key == MAP_KEY_ROUTE_30:
        return (gs.player.x, min(gs.player.y + 2, 12))
    if gs.map_key == MAP_KEY_ROUTE_29:
        return (0, gs.player.y)
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        from src.memory.landmarks import (
            ELMS_LAB_ENTRANCE_ID,
            find_landmark,
            landmark_coords,
            landmark_known,
        )

        landmarks = list(state.get("known_landmarks", []))
        if landmark_known(landmarks, ELMS_LAB_ENTRANCE_ID):
            landmark = find_landmark(landmarks, landmark_id=ELMS_LAB_ENTRANCE_ID)
            if landmark is not None:
                return landmark_coords(landmark)
        return (6, 3)
    return None


def resolve_retired_geography(gs: GameState, state: dict[str, Any] | None = None) -> tuple[int, int] | None:
    """Resolve retired quest geography: landmark coords when map matches, else grid frontier."""
    from src.memory.landmarks import find_landmark, landmark_coords, landmark_known

    state = state or {}
    egg_return = resolve_egg_return_geography(gs, state)
    if egg_return is not None:
        return egg_return
    landmark_id = retired_geography_landmark_id(gs, state)
    if landmark_id is None:
        return None
    axis = _frontier_for_landmark_id(landmark_id)
    landmarks = list(state.get("known_landmarks", []))
    if landmark_known(landmarks, landmark_id):
        landmark = find_landmark(landmarks, landmark_id=landmark_id)
        if landmark is not None and landmark.get("map_key") == gs.map_key:
            return landmark_coords(landmark)
    return _frontier_exploration_target(gs, axis=axis)