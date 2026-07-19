"""Landmark-id hints for post-starter geography (no coordinate routing)."""

from __future__ import annotations

from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_ELMS_LAB,
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
        CHERRYGROVE_EAST_EXIT_ID,
        CHERRYGROVE_NORTH_EXIT_ID,
        ELMS_LAB_ENTRANCE_ID,
        NEW_BARK_WEST_EXIT_ID,
        ROUTE_29_EAST_EXIT_ID,
        ROUTE_29_WEST_EXIT_ID,
        ROUTE_30_NORTH_GATE_ID,
        ROUTE_30_SOUTH_EXIT_ID,
        ROUTE_30_TO_ROUTE_31_ID,
        ROUTE_31_WEST_GATE_ID,
        VIOLET_GYM_ENTRANCE_ID,
    )

    from src.graph.phases import starter_quest

    if not state.get("house_exit_complete"):
        return None
    if state.get("starter_quest_complete"):
        # Post-egg / post-rival: leave lab first, then New Bark west corridor.
        if gs.map_key == MAP_KEY_ELMS_LAB:
            from src.memory.landmarks import ELMS_LAB_EXIT_ID

            return ELMS_LAB_EXIT_ID
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return NEW_BARK_WEST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_29:
            # First (and post-rival) crossing is west into Cherrygrove — not the
            # mid-map "north gate" interim that pulled agents back to (14,14).
            return ROUTE_29_WEST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_30:
            return ROUTE_30_TO_ROUTE_31_ID
        if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
            return CHERRYGROVE_NORTH_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_31:
            return ROUTE_31_WEST_GATE_ID
        if gs.map_key == "26:11":
            # Inside R31–Violet gate: walk west warps into Violet City.
            from src.memory.landmarks import ROUTE_31_VIOLET_GATE_WEST_ID

            return ROUTE_31_VIOLET_GATE_WEST_ID
        if gs.map_key == MAP_KEY_VIOLET_CITY:
            return VIOLET_GYM_ENTRANCE_ID
        return None
    has_egg = bool((gs.raw_metadata or {}).get("has_mystery_egg"))
    egg_delivered = bool((gs.raw_metadata or {}).get("egg_delivered"))
    rival_pending = bool((gs.raw_metadata or {}).get("cherrygrove_rival_pending"))
    # Egg implies starter — do not gate on has_starter() RAM (live Silver can
    # report party_count quirks while EVENT_GOT_MYSTERY_EGG is set).
    if has_egg and not egg_delivered:
        # Egg return: Route 30 south → Cherrygrove east (rival at x=33) → R29 → lab.
        if gs.map_key == MAP_KEY_ROUTE_30:
            return ROUTE_30_SOUTH_EXIT_ID
        if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
            return CHERRYGROVE_EAST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_29:
            return ROUTE_29_EAST_EXIT_ID
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return ELMS_LAB_ENTRANCE_ID
        return None
    # Skipped or unfinished Cherrygrove rival (scene still MEET_RIVAL): re-enter
    # Cherrygrove from the east so coord_events (33,6)/(33,7) can fire.
    if rival_pending and (has_egg or egg_delivered):
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return NEW_BARK_WEST_EXIT_ID
        if gs.map_key == MAP_KEY_ROUTE_29:
            return ROUTE_29_WEST_EXIT_ID
        if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
            return CHERRYGROVE_EAST_EXIT_ID
        return None
    has_starter = starter_quest.has_starter(gs)
    if not has_starter:
        return None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        return NEW_BARK_WEST_EXIT_ID
    if gs.map_key == MAP_KEY_ROUTE_29:
        return ROUTE_29_WEST_EXIT_ID
    if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
        # Pre-egg: Cherrygrove is on the Mr. Pokemon path (north → Route 30).
        return CHERRYGROVE_NORTH_EXIT_ID
    if gs.map_key == MAP_KEY_ROUTE_30:
        return ROUTE_30_NORTH_GATE_ID
    return None
