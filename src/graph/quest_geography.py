"""Landmark-id hints for post-starter geography (no coordinate routing)."""

from __future__ import annotations

from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
)
from src.state.models import GameState


def retired_geography_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    """Landmark id for retired phase geography on the current map, if applicable."""
    from src.memory.landmarks import (
        NEW_BARK_WEST_EXIT_ID,
        ROUTE_29_NORTH_GATE_ID,
        ROUTE_30_NORTH_GATE_ID,
    )

    from src.graph.phases import starter_quest

    if not state.get("house_exit_complete"):
        return None
    if state.get("starter_quest_complete"):
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return NEW_BARK_WEST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_29:
            return ROUTE_29_NORTH_GATE_ID
        if gs.map_key == MAP_KEY_ROUTE_30:
            return ROUTE_30_NORTH_GATE_ID
        return None
    has_starter = starter_quest.has_starter(gs)
    if not has_starter:
        return None
    has_egg = bool((gs.raw_metadata or {}).get("has_mystery_egg"))
    if has_egg:
        return None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        return NEW_BARK_WEST_EXIT_ID
    if gs.map_key == MAP_KEY_ROUTE_29:
        return ROUTE_29_NORTH_GATE_ID
    if gs.map_key == MAP_KEY_ROUTE_30:
        return ROUTE_30_NORTH_GATE_ID
    return None
