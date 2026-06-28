"""Tests for early-game progression logic."""

from __future__ import annotations

from src.graph.nodes import (
    _decompose_subgoals,
    _hold_phase_satisfied,
    _navigation_target,
    navigator_node,
)
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from src.state.models import GameState


def test_route_29_subgoals():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 20},
        raw_metadata={"has_starter": True},
    )
    state = {"house_exit_complete": True}
    subgoals = _decompose_subgoals(gs, state)
    assert any("Route 29" in s or "Cherrygrove" in s or "Mr. Pokemon" in s for s in subgoals)


def test_navigation_target_route_29():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 10, "y": 20})
    state = {"house_exit_complete": True}
    target = _navigation_target(gs, state=state)
    assert target[1] == gs.player.y - 2


def test_hold_phase_false_post_house_starter_active():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert _hold_phase_satisfied(gs, state) is False


def test_navigation_target_post_house_targets_lab():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    target = _navigation_target(gs, state=state)
    assert target == starter_quest.NEW_BARK_LAB_APPROACH


def test_navigator_west_of_lab_door_moves_right_not_up(monkeypatch):
    """Path/heuristic must beat LLM picking blocked 'up' from (5,4)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 5, "y": 4},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True

    def bad_navigate(*_args, **_kwargs):
        return "up"

    monkeypatch.setattr("src.graph.nodes.llm_navigate", bad_navigate)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_right"
    assert result["last_action_result"]["target"] == starter_quest.NEW_BARK_LAB_APPROACH


def test_navigator_at_lab_approach_moves_up(monkeypatch):
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 6, "y": 4},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True

    def bad_navigate(*_args, **_kwargs):
        return "right"

    monkeypatch.setattr("src.graph.nodes.llm_navigate", bad_navigate)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_up"
    assert result["last_action_result"]["target"] == starter_quest.NEW_BARK_LAB_WARP


def test_navigator_post_house_targets_lab(post_house_ram: dict):
    """Post house-exit: navigator moves toward lab warp, not naive east drift."""
    gs = GoldStateReader(ByteArrayReader(post_house_ram)).read()
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["last_action_result"]["target"] == starter_quest.NEW_BARK_LAB_APPROACH


def test_navigator_with_starter_moves_east(new_bark_ram: dict):
    """With starter flag set, navigator picks eastward movement."""
    from src.state.gold_state_reader import ADDR_EVENT_FLAGS
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM

    mem = dict(new_bark_ram)
    flag_addr = ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)
    mem[flag_addr] = mem.get(flag_addr, 0) | (1 << (EVENT_GOT_A_POKEMON_FROM_ELM % 8))
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    result = navigator_node(state)
    assert result["last_action"] == "navigate_right"
    assert result["last_action_result"]["target"][0] > gs.player.x