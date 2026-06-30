"""Tests for high-ROI memory improvements (M1/M3/M4/M5/M7/M11)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.graph.llm import (
    describe_last_failed_action,
    format_episode_memory_for_prompt,
    format_short_term_context,
    llm_plan,
)
from src.graph.nodes import (
    STUCK_ARBITRATION_THRESHOLD,
    critic_node,
    expand_candidates_on_stuck,
    navigation_arbitration_active,
    navigation_repeat_detected,
    navigator_node,
    reorder_candidates_visit_aware,
    repeating_nav_direction,
    score_visit_aware_candidate,
    select_navigation_action,
    visit_aware_path_step,
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
    state["active_subgoal"] = "Exit New Bark east"
    state["last_action_result"] = {"target": (12, 12)}
    text = format_short_term_context(state)
    assert "Active subgoal: Exit New Bark east" in text
    assert "Navigation target: (12,12)" in text
    assert "Recent actions:" in text
    assert "navigate:right@8,12" in text
    assert "Stuck count: 5" in text
    assert "Critic: replan" in text
    assert "Detected loop" in text
    assert describe_last_failed_action(state) == "right"


def test_navigation_repeat_detected_same_tile_same_direction():
    history = ["navigate:right@9,12"] * 3
    assert navigation_repeat_detected(history) is True
    assert repeating_nav_direction(history) == "right"
    assert navigation_repeat_detected(history, min_count=4) is False


def test_navigation_arbitration_active_at_threshold_or_repeat():
    state = initial_agent_state(GameState())
    state["short_term_history"] = ["navigate:right@9,12"] * 3
    assert navigation_arbitration_active(STUCK_ARBITRATION_THRESHOLD, state) is True
    assert navigation_arbitration_active(0, state) is True
    assert navigation_arbitration_active(0, {"short_term_history": []}) is False


def test_select_navigation_action_prefers_llm_when_stuck():
    gs = GameState(player={"x": 8, "y": 12})
    state = initial_agent_state(gs)
    low = select_navigation_action(
        door_exit=None,
        path=["right"],
        llm_choice="up",
        candidates=["right", "up"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=(10, 12),
    )
    mid = select_navigation_action(
        door_exit=None,
        path=["right"],
        llm_choice="up",
        candidates=["right", "up"],
        stuck_count=STUCK_ARBITRATION_THRESHOLD,
        gs=gs,
        state=state,
        target=(10, 12),
    )
    high = select_navigation_action(
        door_exit=None,
        path=["right"],
        llm_choice="up",
        candidates=["right", "up"],
        stuck_count=1,
        gs=gs,
        state=state,
        target=(10, 12),
    )
    assert low == "up"
    assert mid == "up"
    assert high == "right"


def test_select_navigation_action_breaks_same_direction_repeat_without_llm():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 9, "y": 12})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:right@9,12"] * 3
    state["visited_positions"] = [f"{gs.map_key}:9:12", f"{gs.map_key}:10:12"]
    action = select_navigation_action(
        door_exit=None,
        path=["right"],
        llm_choice=None,
        candidates=["right", "up", "down", "left"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(12, 12),
    )
    assert action != "right"


def test_expand_candidates_on_stuck_adds_walkable_cardinals():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 9, "y": 12})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:right@9,12"] * 3
    expanded = expand_candidates_on_stuck(gs, ["right"], state, stuck_count=0)
    assert "right" in expanded
    assert len(expanded) > 1


def test_select_navigation_action_visit_aware_path_when_not_stuck():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = initial_agent_state(gs)
    state["visited_positions"] = [f"{gs.map_key}:9:12"]
    action = select_navigation_action(
        door_exit=None,
        path=["right", "left"],
        llm_choice=None,
        candidates=["right", "left"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(10, 12),
    )
    assert action == "left"


def test_visit_aware_path_step_prefers_unvisited_over_path_zero():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = initial_agent_state(gs)
    state["visited_positions"] = [f"{gs.map_key}:9:12"]
    step = visit_aware_path_step(["right", "left"], gs, state)
    assert step == "left"


def test_select_navigation_action_preserves_door_exit_priority():
    gs = GameState(player={"x": 8, "y": 12})
    state = initial_agent_state(gs)
    action = select_navigation_action(
        door_exit="down",
        path=["right"],
        llm_choice="up",
        candidates=["right", "up", "down"],
        stuck_count=10,
        gs=gs,
        state=state,
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


def test_capture_stuck_episode_uses_summarize_history_and_retrieve_guarded():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = _stuck_state(gs)
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        with patch.object(mem, "summarize_history", wraps=mem.summarize_history) as summarize:
            fact = mem.capture_stuck_episode(state, gs)
            summarize.assert_called_once()
        assert fact.startswith("stuck@24:4:")
        assert fact in state["long_term_facts"]
        assert fact in mem.get_facts()
        assert len(mem.retrieve("24:4 stuck", allow_fallback=False)) >= 1
        assert mem.retrieve("unrelated query xyz", allow_fallback=False) == []


def test_hydrate_state_loads_facts_into_episode_prompt():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 8, "y": 12, "map_name": "New Bark Town"},
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_fact("stuck@24:4:right-left:3")
        mem.add_summary("24:4 stuck loop near lab")
        state = initial_agent_state(gs)
        state["stuck_count"] = 5
        state["should_replan"] = True
        hydrated = mem.hydrate_state(state)
        assert "stuck@24:4:right-left:3" in hydrated["long_term_facts"]
        text = format_episode_memory_for_prompt(hydrated, gs, memory=mem)
        assert "Known facts:" in text
        assert "stuck@24:4:right-left:3" in text
        assert "Past episodes:" in text


def test_format_episode_memory_uses_guarded_retrieve_not_fallback():
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
    state["stuck_count"] = STUCK_ARBITRATION_THRESHOLD
    result = navigator_node(state)
    assert result["last_action"] == "navigate_left"


def test_format_episode_memory_at_arbitration_threshold():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 8, "y": 12, "map_name": "New Bark Town"},
    )
    state = initial_agent_state(gs)
    state["stuck_count"] = STUCK_ARBITRATION_THRESHOLD
    state["long_term_facts"] = ["stuck@24:4:right-left:2"]
    text = format_episode_memory_for_prompt(state, gs)
    assert "Known facts:" in text