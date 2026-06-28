"""Tests for high-ROI memory improvements (M1/M3/M4/M5/M7/M11)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.llm import (
    describe_last_failed_action,
    format_episode_memory_for_prompt,
    format_short_term_context,
    llm_plan,
)
from src.graph.nodes import (
    critic_node,
    navigator_node,
    reorder_candidates_visit_aware,
    score_visit_aware_candidate,
    select_navigation_action,
)
from src.graph.state import initial_agent_state
from src.memory.long_term_memory import LongTermMemory
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from src.state.models import GameState


def _stuck_state(gs: GameState) -> dict:
    state = initial_agent_state(gs)
    state["short_term_history"] = [
        "navigate:right@8,12",
        "navigate:left@8,12",
        "navigate:right@8,12",
        "navigate:left@8,12",
        "navigate:right@8,12",
    ]
    state["stuck_count"] = 5
    state["critic_verdict"] = "replan"
    state["critic_notes"] = "Detected loop or high stuck count"
    state["should_replan"] = True
    state["long_term_facts"] = ["stuck@24:4:right-left-right:5"]
    return state


def test_format_short_term_context_includes_history_critic_stuck():
    gs = GameState(player={"x": 8, "y": 12})
    state = _stuck_state(gs)
    text = format_short_term_context(state)
    assert "Recent actions:" in text
    assert "navigate:right@8,12" in text
    assert "Stuck count: 5" in text
    assert "Critic: replan" in text
    assert "Detected loop" in text
    assert describe_last_failed_action(state) == "right"


def test_select_navigation_action_prefers_llm_when_stuck():
    gs = GameState(player={"x": 8, "y": 12})
    low = select_navigation_action(
        door_exit=None,
        path=["right"],
        llm_choice="up",
        candidates=["right", "up"],
        stuck_count=5,
        gs=gs,
        target=(10, 12),
    )
    high = select_navigation_action(
        door_exit=None,
        path=["right"],
        llm_choice="up",
        candidates=["right", "up"],
        stuck_count=1,
        gs=gs,
        target=(10, 12),
    )
    assert low == "up"
    assert high == "right"


def test_select_navigation_action_preserves_door_exit_priority():
    gs = GameState(player={"x": 8, "y": 12})
    action = select_navigation_action(
        door_exit="down",
        path=["right"],
        llm_choice="up",
        candidates=["right", "up", "down"],
        stuck_count=10,
        gs=gs,
        target=(10, 12),
    )
    assert action == "down"


def test_visit_aware_scoring_prefers_unvisited_tile():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = initial_agent_state(gs)
    state["visited_positions"] = [f"{gs.map_key}:9:12"]
    unvisited = score_visit_aware_candidate("left", gs, state)
    visited = score_visit_aware_candidate("right", gs, state)
    assert unvisited > visited


def test_reorder_candidates_visit_aware_puts_unvisited_first():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = initial_agent_state(gs)
    state["visited_positions"] = [f"{gs.map_key}:9:12"]
    ordered = reorder_candidates_visit_aware(gs, ["right", "left"], state)
    assert ordered[0] == "left"


def test_capture_stuck_episode_records_fact_and_summary():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = _stuck_state(gs)
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        fact = mem.capture_stuck_episode(state, gs)
        assert fact.startswith("stuck@24:4:")
        assert fact in state["long_term_facts"]
        assert fact in mem.get_facts()
        assert len(mem.retrieve_relevant("24:4 stuck")) >= 1


def test_format_episode_memory_includes_facts_and_guarded_retrieve():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12, "map_name": "New Bark Town"})
    state = _stuck_state(gs)
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_summary("stuck loop on New Bark Town near lab door")
        mem.add_summary("unrelated battle on Route 30")
        text = format_episode_memory_for_prompt(state, gs, memory=mem)
        assert "Known facts:" in text
        assert "stuck@24:4" in text
        assert "Past episodes:" in text
        assert "New Bark" in text
        assert "Route 30" not in text


def test_critic_replan_captures_stuck_episode(monkeypatch):
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = _stuck_state(gs)
    state["stuck_count"] = 12
    captured: list[str] = []

    def fake_capture(st: dict, _gs: GameState) -> None:
        captured.append("called")

    monkeypatch.setattr("src.graph.nodes._capture_stuck_episode", fake_capture)
    critic_node(state)
    assert captured == ["called"]


def test_llm_plan_prompt_includes_memory_context(new_bark_ram: dict, monkeypatch):
    captured: list[str] = []

    class FakeLLM:
        def invoke(self, messages, config=None):
            captured.append(messages[1].content)
            return type("R", (), {"content": "subgoal one\nsubgoal two\nsubgoal three"})()

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr("src.graph.llm.get_chat_model", lambda: FakeLLM())

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = _stuck_state(gs)
    result = llm_plan(gs, state)
    assert result is not None
    prompt = captured[0]
    assert "Stuck count: 5" in prompt
    assert "Known facts:" in prompt
    assert "navigate:right" in prompt


def test_navigator_prefers_llm_choice_when_stuck(new_bark_ram: dict, monkeypatch):
    monkeypatch.setattr("src.graph.nodes.find_path", lambda *a, **k: ["right"])
    monkeypatch.setattr(
        "src.graph.nodes._navigation_candidates",
        lambda gs, target, path, state=None: ["left", "right"],
    )
    monkeypatch.setattr("src.graph.nodes.llm_navigate", lambda *a, **k: "left")

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    state["stuck_count"] = 5
    result = navigator_node(state)
    assert result["last_action"] == "navigate_left"