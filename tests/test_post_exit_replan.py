"""Post house-exit: LLM planner blocked on New Bark; critic stuck logic intact."""

from __future__ import annotations

from src.graph.nodes import critic_node, planner_node, supervisor_node
from src.graph.phases import house_exit
from src.graph.state import initial_agent_state
from src.state.models import GameState


def _new_bark_at(x: int, y: int) -> GameState:
    return GameState(
        player={"map_group": 24, "map_id": 4, "x": x, "y": y, "map_name": "New Bark Town"},
    )


def test_planner_blocks_llm_post_exit():
    gs = _new_bark_at(17, 6)
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    assert house_exit.planner_allows_llm(gs, state) is False


def test_critic_replans_on_stuck_post_exit():
    gs = _new_bark_at(17, 6)
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["stuck_count"] = 10
    state["short_term_history"] = [
        "navigate:right@17,6",
        "navigate:right@17,6",
        "navigate:right@17,6",
    ]
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_supervisor_routes_to_planner_when_stuck_post_exit():
    gs = _new_bark_at(17, 6)
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["stuck_count"] = 10
    state["should_replan"] = True
    result = supervisor_node(state)
    assert result["next_node"] == "planner"


def test_planner_keeps_heuristic_subgoals_post_exit():
    gs = _new_bark_at(17, 6)
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["should_replan"] = True
    result = planner_node(state)
    assert "Route 29" in result["active_subgoal"] or "New Bark" in result["active_subgoal"]
    assert "Mom" not in result["active_subgoal"]