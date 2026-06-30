"""Parametrized matrix for retired quest geography resolution."""

from __future__ import annotations

import pytest

from src.graph.quest_geography import resolve_retired_geography
from src.memory.landmarks import (
    NEW_BARK_EAST_EXIT_ID,
    ROUTE_29_NORTH_GATE_ID,
    ROUTE_30_NORTH_GATE_ID,
    make_landmark,
)
from src.state.models import GameState


def _state(*, house_exit_complete: bool = True, landmarks: list | None = None) -> dict:
    return {
        "house_exit_complete": house_exit_complete,
        "known_landmarks": list(landmarks or []),
    }


@pytest.mark.parametrize(
    "gs_kwargs,landmarks,expected",
    [
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            None,
            (19, 12),
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            [
                make_landmark(
                    landmark_id=NEW_BARK_EAST_EXIT_ID,
                    name="east exit",
                    map_key="24:4",
                    x=19,
                    y=12,
                    kind="map_visit",
                )
            ],
            (19, 12),
        ),
        (
            {"map_group": 24, "map_id": 4, "x": 13, "y": 6},
            [
                make_landmark(
                    landmark_id=NEW_BARK_EAST_EXIT_ID,
                    name="east exit",
                    map_key="24:3",
                    x=10,
                    y=12,
                    kind="map_visit",
                )
            ],
            (19, 12),
        ),
        (
            {"map_group": 24, "map_id": 3, "x": 10, "y": 12},
            None,
            (10, 5),
        ),
        (
            {"map_group": 24, "map_id": 3, "x": 10, "y": 12},
            [
                make_landmark(
                    landmark_id=ROUTE_29_NORTH_GATE_ID,
                    name="route 29 gate",
                    map_key="24:3",
                    x=10,
                    y=5,
                    kind="map_visit",
                )
            ],
            (10, 5),
        ),
        (
            {"map_group": 24, "map_id": 3, "x": 10, "y": 12},
            [
                make_landmark(
                    landmark_id=ROUTE_29_NORTH_GATE_ID,
                    name="route 29 gate",
                    map_key="24:4",
                    x=19,
                    y=12,
                    kind="map_visit",
                )
            ],
            (10, 5),
        ),
        (
            {"map_group": 26, "map_id": 1, "x": 10, "y": 8},
            None,
            (10, 3),
        ),
        (
            {"map_group": 26, "map_id": 1, "x": 10, "y": 8},
            [
                make_landmark(
                    landmark_id=ROUTE_30_NORTH_GATE_ID,
                    name="route 30 gate",
                    map_key="26:1",
                    x=10,
                    y=3,
                    kind="map_visit",
                )
            ],
            (10, 3),
        ),
        (
            {"map_group": 26, "map_id": 1, "x": 10, "y": 8},
            [
                make_landmark(
                    landmark_id=ROUTE_30_NORTH_GATE_ID,
                    name="route 30 gate",
                    map_key="24:3",
                    x=10,
                    y=5,
                    kind="map_visit",
                )
            ],
            (10, 3),
        ),
    ],
)
def test_resolve_retired_geography_matrix(gs_kwargs, landmarks, expected):
    gs = GameState(
        player=gs_kwargs,
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = _state(landmarks=landmarks)
    assert resolve_retired_geography(gs, state) == expected


def test_resolve_retired_geography_returns_none_outside_quest_context():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    assert resolve_retired_geography(gs, _state()) is None


def test_resolve_retired_geography_post_rival_with_mystery_egg_flag():
    """After rival, egg possession must not block east/north retired geography."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": True, "has_mystery_egg": True, "egg_delivered": True},
        party_count=1,
    )
    state = _state()
    state["starter_quest_complete"] = True
    assert resolve_retired_geography(gs, state) == (19, 12)


def test_resolve_retired_geography_no_recursion_on_wrong_map_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = _state(
        landmarks=[
            make_landmark(
                landmark_id=NEW_BARK_EAST_EXIT_ID,
                name="east exit",
                map_key="24:4",
                x=19,
                y=12,
                kind="map_visit",
            )
        ]
    )
    assert resolve_retired_geography(gs, state) == (10, 5)