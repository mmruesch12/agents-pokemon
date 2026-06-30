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


def test_supervisor_routes_to_navigator(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    state["bootstrap_complete"] = True
    result = supervisor_node(state)
    assert result["next_node"] == "navigator"


def test_supervisor_routes_to_planner_when_stuck(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    state["bootstrap_complete"] = True
    state["stuck_count"] = 12
    result = supervisor_node(state)
    assert result["next_node"] == "planner"
    assert result["should_replan"] is True


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


def test_navigator_new_bark_moves_right(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_right"
    assert result["last_action_result"]["direction"] == "right"
    assert result["next_node"] == "critic"


def test_battler_fight_when_healthy(battle_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    gs = GoldStateReader(ByteArrayReader(battle_ram)).read()
    state = _state_with_game(gs)
    result = battler_node(state)
    assert result["last_action"] == "battle_fight"


def test_critic_replan_routes_to_memory_not_planner():
    gs = GameState()
    state = _state_with_game(gs)
    state["short_term_history"] = ["navigate:right@8,12"] * 5
    state["stuck_count"] = 12
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True
    assert result["next_node"] == "memory"


def test_critic_repetition_requires_stuck_count():
    gs = GameState()
    state = _state_with_game(gs)
    state["short_term_history"] = ["navigate:right@8,12"] * 3
    state["stuck_count"] = 1
    result = critic_node(state)
    assert result["critic_verdict"] == "proceed"
    assert result["next_node"] == "memory"


def test_critic_replan_on_navigate_interact_oscillation():
    gs = GameState()
    state = _state_with_game(gs)
    state["short_term_history"] = [
        "navigate:down@3,5",
        "interact:a@3,5",
        "navigate:down@3,5",
        "interact:a@3,5",
        "navigate:down@3,5",
        "interact:a@3,5",
    ]
    state["stuck_count"] = 1
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_critic_replan_on_interact_only_spam_at_ball():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = _state_with_game(gs)
    state["short_term_history"] = ["interact:a@5,3"] * 6
    state["stuck_count"] = 3
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_critic_replan_on_nav_nav_interact_lab_pattern():
    """Match INDOOR_INTERACT_STUCK rhythm: two failed navigates then interact."""
    gs = GameState(player={"map_group": 24, "map_id": 5, "x": 5, "y": 3})
    state = _state_with_game(gs)
    cycle = [
        "navigate:right@5,3",
        "navigate:right@5,3",
        "interact:a@5,3",
    ]
    state["short_term_history"] = cycle * 3
    state["stuck_count"] = 2
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_memory_increments_steps(gold_reader):
    gs = gold_reader.read()
    state = _state_with_game(gs)
    result = memory_node(state)
    assert result["metrics"]["steps"] == 1
    assert result["next_node"] == "supervisor"


def test_memory_milestone_route_29():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 10, "y": 20})
    state = _state_with_game(gs)
    state["maps_visited"] = ["24:3"]
    result = memory_node(state)
    assert "Reached Route 29" in result["milestones"]


def test_memory_milestone_badge_earned():
    gs = GameState(johto_badges=1, badge_names=["Zephyr"])
    state = _state_with_game(gs)
    state["badges_at_last_check"] = 0
    result = memory_node(state)
    assert any("Earned badge" in m for m in result["milestones"])
    assert result["badges_at_last_check"] == 1