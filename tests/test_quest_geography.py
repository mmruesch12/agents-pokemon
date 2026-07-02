"""Landmark-id hints for post-starter geography (no coordinate resolvers)."""

from __future__ import annotations

import pytest

from src.graph.quest_geography import retired_geography_landmark_id
from src.memory.landmarks import (
    NEW_BARK_EAST_EXIT_ID,
    ROUTE_29_NORTH_GATE_ID,
    ROUTE_30_NORTH_GATE_ID,
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
            NEW_BARK_EAST_EXIT_ID,
        ),
        (
            {"map_group": 24, "map_id": 3, "x": 10, "y": 12},
            {"has_starter": True},
            {},
            ROUTE_29_NORTH_GATE_ID,
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
            None,
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            {"has_starter": True, "has_mystery_egg": True, "egg_delivered": True},
            {"starter_quest_complete": True},
            NEW_BARK_EAST_EXIT_ID,
        ),
    ],
)
def test_retired_geography_landmark_id(gs_kwargs, meta, state_kwargs, expected):
    party = 1 if meta.get("has_starter") else 0
    gs = GameState(player=gs_kwargs, raw_metadata=meta, party_count=party)
    state = _state(**state_kwargs)
    assert retired_geography_landmark_id(gs, state) == expected