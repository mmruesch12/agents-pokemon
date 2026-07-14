"""Landmark-id hints for post-starter geography (no coordinate routing)."""

from __future__ import annotations

from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
    MAP_KEY_ROUTE_31,
    MAP_KEY_VIOLET_CITY,
)
from src.state.models import GameState


def retired_geography_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    """Landmark id for retired phase geography on the current map, if applicable."""
    from src.memory.landmarks import (
        CHERRYGROVE_NORTH_EXIT_ID,
        NEW_BARK_WEST_EXIT_ID,
        ROUTE_29_NORTH_GATE_ID,
        ROUTE_30_NORTH_GATE_ID,
        ROUTE_30_TO_ROUTE_31_ID,
        ROUTE_31_WEST_GATE_ID,
        VIOLET_GYM_ENTRANCE_ID,
    )

    from src.graph.phases import starter_quest

    if not state.get("house_exit_complete"):
        return None
    if state.get("starter_quest_complete"):
        # Post-rival corridor: New Bark → R29 → R30/Cherry → R31 → Violet → gym
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return NEW_BARK_WEST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_29:
            return ROUTE_29_NORTH_GATE_ID
        if gs.map_key == MAP_KEY_ROUTE_30:
            return ROUTE_30_TO_ROUTE_31_ID
        if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
            return CHERRYGROVE_NORTH_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_31:
            return ROUTE_31_WEST_GATE_ID
        if gs.map_key == MAP_KEY_VIOLET_CITY:
            return VIOLET_GYM_ENTRANCE_ID
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
    if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
        # Pre-egg: Cherrygrove is on the Mr. Pokemon path (north → Route 30).
        return CHERRYGROVE_NORTH_EXIT_ID
    if gs.map_key == MAP_KEY_ROUTE_30:
        return ROUTE_30_NORTH_GATE_ID
    return None
