"""Tests for early-game progression logic."""

from __future__ import annotations

from src.graph.nodes import _decompose_subgoals, _navigation_target, navigator_node
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from src.state.models import GameState


def test_route_29_subgoals():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 10, "y": 20})
    subgoals = _decompose_subgoals(gs)
    assert any("Route 29" in s or "Cherrygrove" in s for s in subgoals)


def test_navigation_target_route_29():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 10, "y": 20})
    target = _navigation_target(gs)
    assert target[1] == gs.player.y - 2


def test_navigator_progression_from_start(new_bark_ram: dict):
    """Direct exercise: from New Bark start state, navigator picks eastward movement."""
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_right"
    assert result["last_action_result"]["target"][0] > gs.player.x