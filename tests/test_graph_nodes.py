"""Tests for graph nodes - direct invocation without mocks."""

from __future__ import annotations

from src.graph.nodes import (
    battler_node,
    critic_node,
    memory_node,
    navigator_node,
    planner_node,
    supervisor_node,
)
from src.graph.state import initial_agent_state
from src.state.models import GameState


def _state_with_game(gs: GameState) -> dict:
    return initial_agent_state(gs)


def test_supervisor_routes_to_navigator():
    gs = GameState()
    state = _state_with_game(gs)
    result = supervisor_node(state)
    assert result["next_node"] == "navigator"


def test_supervisor_routes_to_battler_in_battle(battle_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    gs = GoldStateReader(ByteArrayReader(battle_ram)).read()
    state = _state_with_game(gs)
    result = supervisor_node(state)
    assert result["next_node"] == "battler"
    assert result["phase"] == "battle"


def test_planner_decomposes_subgoals(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    result = planner_node(state)
    assert len(result["current_plan"]) >= 2
    assert len(result["subgoals"]) >= 1
    assert result["next_node"] == "navigator"


def test_navigator_produces_action(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["next_node"] == "critic"


def test_battler_fight_when_healthy(battle_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    gs = GoldStateReader(ByteArrayReader(battle_ram)).read()
    state = _state_with_game(gs)
    result = battler_node(state)
    assert result["last_action"] == "battle_fight"


def test_critic_detects_loop():
    gs = GameState()
    state = _state_with_game(gs)
    state["short_term_history"] = ["navigate:right"] * 5
    state["stuck_count"] = 12
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_memory_increments_steps(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    result = memory_node(state)
    assert result["metrics"]["steps"] == 1
    assert result["next_node"] == "supervisor"