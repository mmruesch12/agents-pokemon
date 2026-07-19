"""Landmark-id hints for post-starter geography (no coordinate resolvers)."""

from __future__ import annotations

import pytest

from src.graph.quest_geography import retired_geography_landmark_id
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
from src.state.models import GameState


def _state(**kwargs) -> dict:
    base = {
        "house_exit_complete": True,
        "starter_quest_complete": False,
        "known_landmarks": [],
    }
    base.update(kwargs)
    return base


@pytest.mark.parametrize(
    "gs_kwargs,meta,state_kwargs,expected",
    [
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            {"has_starter": True},
            {},
            NEW_BARK_WEST_EXIT_ID,
        ),
        (
            {"map_group": 24, "map_id": 3, "x": 10, "y": 12},
            {"has_starter": True},
            {},
            ROUTE_29_WEST_EXIT_ID,
        ),
        (
            {"map_group": 26, "map_id": 1, "x": 10, "y": 8},
            {"has_starter": True},
            {},
            ROUTE_30_NORTH_GATE_ID,
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            {"has_starter": True},
            {"house_exit_complete": False},
            None,
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            {"has_starter": False},
            {},
            None,
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            {"has_starter": True, "has_mystery_egg": True},
            {},
            ELMS_LAB_ENTRANCE_ID,
        ),
        (
            {"map_group": 26, "map_id": 1, "x": 14, "y": 23},
            {"has_starter": True, "has_mystery_egg": True},
            {},
            ROUTE_30_SOUTH_EXIT_ID,
        ),
        (
            {"map_group": 26, "map_id": 3, "x": 17, "y": 5},
            {"has_starter": True, "has_mystery_egg": True},
            {},
            CHERRYGROVE_EAST_EXIT_ID,
        ),
        (
            {"map_group": 24, "map_id": 3, "x": 10, "y": 8},
            {"has_starter": True, "has_mystery_egg": True},
            {},
            ROUTE_29_EAST_EXIT_ID,
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            {"has_starter": True, "has_mystery_egg": True, "egg_delivered": True},
            {"starter_quest_complete": True},
            NEW_BARK_WEST_EXIT_ID,
        ),
        (
            {"map_group": 26, "map_id": 1, "x": 10, "y": 8},
            {"has_starter": True},
            {"starter_quest_complete": True},
            ROUTE_30_TO_ROUTE_31_ID,
        ),
        (
            {"map_group": 26, "map_id": 3, "x": 17, "y": 5},
            {"has_starter": True},
            {"starter_quest_complete": True},
            CHERRYGROVE_NORTH_EXIT_ID,
        ),
        (
            {"map_group": 26, "map_id": 2, "x": 10, "y": 8},
            {"has_starter": True},
            {"starter_quest_complete": True},
            ROUTE_31_WEST_GATE_ID,
        ),
        (
            {"map_group": 10, "map_id": 5, "x": 10, "y": 12},
            {"has_starter": True},
            {"starter_quest_complete": True},
            VIOLET_GYM_ENTRANCE_ID,
        ),
    ],
)
def test_retired_geography_landmark_id(gs_kwargs, meta, state_kwargs, expected):
    party = 1 if meta.get("has_starter") else 0
    gs = GameState(player=gs_kwargs, raw_metadata=meta, party_count=party)
    state = _state(**state_kwargs)
    assert retired_geography_landmark_id(gs, state) == expected

def test_egg_return_r29_targets_east_exit_not_west_gate():
    """Egg-return must not use west gate waypoints; south y14 then New Bark (59,8)."""
    from src.graph.navigation_resolve import resolve_navigation_target
    from src.memory.landmarks import seed_static_map_landmarks
    from src.state.models import GameState
    from src.graph.state import initial_agent_state

    west_trap = {(10, 8), (4, 10), (0, 7)}
    for x, y in ((11, 10), (17, 6), (17, 7), (30, 6), (32, 14), (45, 13)):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": x, "y": y},
            raw_metadata={
                "has_mystery_egg": True,
                "egg_delivered": False,
                "has_starter": True,
            },
            party_count=1,
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        seed_static_map_landmarks(state)
        target = resolve_navigation_target(gs, state)
        assert target not in west_trap, f"{(x, y)}: west trap {target}"
        # Interim south corridor or final east exit
        assert target == (59, 8) or target[1] >= 14, f"{(x, y)}: got {target}"
