"""Tests for post-invoke terminal intent card formatting and runner log site."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.graph import compile_graph
from src.graph.state import initial_agent_state
from src.run.autonomous_runner import format_intent_card
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

RUNNER_SOURCE = Path(__file__).resolve().parents[1] / "src" / "run" / "autonomous_runner.py"


def test_format_intent_card_navigator_example_shape():
    state = {
        "metrics": {"steps": 42},
        "last_action": "navigate_right",
        "active_subgoal": "Exit New Bark Town east",
        "critic_verdict": "proceed",
        "game_state": {
            "player": {"map_name": "New Bark Town", "x": 8, "y": 12},
        },
    }
    card = format_intent_card(state)
    assert card == (
        "[step 42] navigator → navigate_right | "
        "subgoal: Exit New Bark Town east | map: New Bark Town (8,12) | critic: proceed"
    )


def test_format_intent_card_bootstrap_intro_sequence():
    state = {
        "metrics": {"steps": 3},
        "phase": "bootstrap",
        "last_action": "bootstrap_a",
        "active_subgoal": "Leave player house",
        "critic_verdict": "proceed",
        "game_state": {"player": {"map_name": "TITLE", "x": 0, "y": 0}},
    }
    card = format_intent_card(state)
    assert "bootstrap → bootstrap_a" in card
    assert "subgoal: intro sequence" in card
    assert "critic: proceed" in card


def test_format_intent_card_after_graph_invoke(new_bark_ram: dict):
    """Drive real graph.invoke and format the returned state."""
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    state["run_max_steps"] = 1

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(checkpoint_path=Path(tmp) / "intent.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "intent"}})

    card = format_intent_card(result)
    assert card.startswith("[step 1]")
    assert "→" in card
    assert "subgoal:" in card
    assert "map:" in card
    assert "critic:" in card
    assert result["last_action"].startswith("navigate_")
    assert "navigator →" in card


def test_runner_loop_logs_intent_card_after_invoke():
    """Structural: while-loop graph.invoke is immediately followed by intent card log."""
    source = RUNNER_SOURCE.read_text()
    invoke = "state = graph.invoke(state, config=config)"
    assert invoke in source
    idx = source.index(invoke)
    following = source[idx : idx + 200]
    assert "logger.info" in following
    assert "format_intent_card(state)" in following
    while_idx = source.rfind("while state.get", 0, idx)
    assert while_idx != -1
    assert source[while_idx:idx].count("while ") >= 1