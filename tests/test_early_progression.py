"""Tests for early-game progression logic."""

from __future__ import annotations

from src.graph.nodes import (
    _decompose_subgoals,
    _hold_phase_satisfied,
    _navigation_target,
    navigator_node,
)
from src.graph.state import initial_agent_state
from src.memory.landmarks import ELMS_LAB_ENTRANCE_ID, make_landmark
from src.state.models import GameState


def _lab_landmark_state(gs: GameState, *, x: int = 6, y: int = 3) -> dict:
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=ELMS_LAB_ENTRANCE_ID,
            name="Elm's Lab entrance",
            map_key="24:4",
            x=x,
            y=y,
            kind="building_entrance",
        )
    ]
    return state


def test_route_29_subgoals():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 20},
        raw_metadata={"has_starter": True},
    )
    state = {"house_exit_complete": True, "starter_quest_complete": True}
    subgoals = _decompose_subgoals(gs, state)
    assert any("Route 29" in s or "Cherrygrove" in s for s in subgoals)


def test_navigation_target_route_29():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
    )
    state = {"house_exit_complete": True, "starter_quest_complete": True}
    target = _navigation_target(gs, state=state)
    assert target[1] < gs.player.y


def test_hold_phase_false_post_house_starter_active():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert _hold_phase_satisfied(gs, state) is False


def test_navigation_target_post_house_uses_lab_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = _lab_landmark_state(gs)
    target = _navigation_target(gs, state=state)
    assert target == (6, 4)


def test_navigator_west_of_lab_door_moves_right_not_up(monkeypatch):
    """Path/heuristic must beat LLM picking blocked 'up' from (5,4)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 5, "y": 4},
        raw_metadata={"has_starter": False},
    )
    state = _lab_landmark_state(gs, x=6, y=3)

    def bad_navigate(*_args, **_kwargs):
        return "up"

    monkeypatch.setattr("src.graph.nodes.llm_navigate", bad_navigate)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_right"
    assert result["last_action_result"]["target"] == (6, 4)


def test_navigator_at_lab_approach_moves_up(monkeypatch):
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 6, "y": 4},
        raw_metadata={"has_starter": False},
    )
    state = _lab_landmark_state(gs)

    def bad_navigate(*_args, **_kwargs):
        return "right"

    monkeypatch.setattr("src.graph.nodes.llm_navigate", bad_navigate)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_up"
    assert result["last_action_result"]["target"] in ((6, 3), (6, 4))


def test_navigator_post_house_targets_lab_with_landmark(monkeypatch):
    """Post house-exit: navigator moves toward discovered lab entrance."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = _lab_landmark_state(gs)
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["last_action_result"]["target"] == (6, 4)


def test_navigator_with_starter_moves_east():
    """With starter flag set, navigator picks eastward movement."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    from src.memory.landmarks import seed_static_map_landmarks

    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    seed_static_map_landmarks(state)
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["last_action_result"]["target"][0] > gs.player.x
    assert result["last_action_result"]["target"][1] >= gs.player.y