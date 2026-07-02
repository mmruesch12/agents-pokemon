"""Landmark-first navigation target resolution (roadmap Phase 3)."""

from __future__ import annotations

from typing import Any

from src.graph.exploration import exploration_target
from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
)
from src.state.models import GameState
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_EXIT_ID,
    ELMS_LAB_INTERIOR_ID,
    MR_POKEMONS_HOUSE_ENTRANCE_ID,
    find_landmark,
    landmark_coords,
)


def _landmark_target_on_map(
    landmarks: list[dict[str, Any]],
    landmark_id: str,
    map_key: str,
) -> tuple[int, int] | None:
    landmark = find_landmark(landmarks, landmark_id=landmark_id)
    if landmark is None or landmark.get("map_key") != map_key:
        return None
    return landmark_coords(landmark)


def _lab_entrance_approach(
    gs: GameState,
    door: tuple[int, int],
    state: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """South approach tile when west of the discovered lab door."""
    from src.graph.pathfinding import find_path

    px, py = gs.player.x, gs.player.y
    approach = (door[0], door[1] + 1)
    if (px, py) in (door, approach):
        return door
    if py == approach[1] and px < approach[0]:
        return approach
    if find_path(
        px, py, approach[0], approach[1], map_key=gs.map_key, state=state
    ):
        return approach
    return door


def _starter_quest_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    from src.graph.phases import starter_quest
    from src.graph.quest_geography import retired_geography_landmark_id

    if not state.get("house_exit_complete"):
        return None
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_quest.has_starter(gs)
        and not starter_quest._has_egg(gs)
    ):
        return ELMS_LAB_EXIT_ID
    interior_id = starter_quest.interior_landmark_id(gs, state)
    if interior_id is not None:
        return interior_id
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN and not starter_quest.has_starter(gs):
        return ELMS_LAB_ENTRANCE_ID
    if gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE and not starter_quest._has_egg(gs):
        return MR_POKEMONS_HOUSE_ENTRANCE_ID
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_quest._has_egg(gs)
        and not starter_quest._egg_delivered(gs)
    ):
        interior = find_landmark(
            list(state.get("known_landmarks", [])),
            landmark_id=ELMS_LAB_INTERIOR_ID,
        )
        if interior is not None:
            return ELMS_LAB_INTERIOR_ID
    return retired_geography_landmark_id(gs, state)


def resolve_landmark_navigation_target(
    gs: GameState,
    state: dict[str, Any],
) -> tuple[int, int] | None:
    """Resolve target from known_landmarks for the current map and quest stage."""
    landmarks = list(state.get("known_landmarks", []))
    landmark_id = _starter_quest_landmark_id(gs, state)
    if landmark_id:
        coords = _landmark_target_on_map(landmarks, landmark_id, gs.map_key)
        if coords is not None:
            if landmark_id == ELMS_LAB_ENTRANCE_ID:
                return _lab_entrance_approach(gs, coords, state)
            return coords

    return None


def resolve_navigation_target(
    gs: GameState,
    state: dict[str, Any],
    *,
    map_key: str | None = None,
) -> tuple[int, int]:
    """Landmark-first nav target; exploration frontier as fallback."""
    from src.graph.phases import house_exit

    map_key = map_key or gs.map_key
    house_target = house_exit.navigation_target(gs, map_key=map_key, state=state)
    if house_target is not None:
        return house_target

    landmark_target = resolve_landmark_navigation_target(gs, state)
    if landmark_target is not None:
        return landmark_target

    if state.get("starter_quest_complete"):
        from src.graph.phases import early_progression as ep

        if ep.in_early_progression(gs, state):
            return exploration_target(gs, state)

    if state.get("house_exit_complete"):
        return exploration_target(gs, state)

    return (gs.player.x + 1, gs.player.y)
