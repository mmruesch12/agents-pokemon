"""Tests for post-invoke terminal intent card formatting and runner logging."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.graph.graph import compile_graph
from src.graph.state import initial_agent_state
from src.run.autonomous_runner import AutonomousRunner, format_intent_card, log_intent_card
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from tests.fake_emulator import MutableRamEmulator

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


def test_log_intent_card_emits_logger_info(caplog):
    """Shipped logger path: log_intent_card writes format_intent_card at INFO."""
    state = {
        "metrics": {"steps": 7},
        "last_action": "navigate_up",
        "active_subgoal": "Reach lab",
        "critic_verdict": "proceed",
        "game_state": {"player": {"map_name": "New Bark Town", "x": 5, "y": 10}},
    }
    expected = format_intent_card(state)

    with caplog.at_level(logging.INFO, logger="src.run.autonomous_runner"):
        log_intent_card(state)

    assert len(caplog.records) == 1
    assert caplog.records[0].message == expected
    assert caplog.records[0].levelname == "INFO"


def test_runner_loop_calls_log_intent_card_after_invoke():
    """Structural: while-loop graph.invoke is immediately followed by log_intent_card."""
    source = RUNNER_SOURCE.read_text()
    invoke = "state = graph.invoke(state, config=invoke_config)"
    assert invoke in source
    idx = source.index(invoke)
    following = source[idx : idx + 200]
    assert "log_intent_card(state)" in following
    while_idx = source.rfind("while state.get", 0, idx)
    assert while_idx != -1


def test_runner_run_logs_intent_cards_each_loop(new_bark_ram: dict, tmp_path, caplog):
    """AutonomousRunner.run() while-loop logs one [step N] card per graph.invoke."""
    emu = MutableRamEmulator(new_bark_ram)

    def save_state(name: str) -> None:
        pass

    emu.save_state = save_state  # type: ignore[method-assign]

    class FakePyBoyWrapper:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return emu

        def __exit__(self, *args):
            return False

    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"\x00")

    with caplog.at_level(logging.INFO, logger="src.run.autonomous_runner"):
        with patch("src.emulator.pyboy_wrapper.PyBoyWrapper", FakePyBoyWrapper):
            runner = AutonomousRunner(
                rom_path=rom,
                max_steps=3,
                checkpoint_db=tmp_path / "checkpoints.sqlite",
                save_dir=tmp_path / "saves",
            )
            result = runner.run()

    assert result["steps"] == 3
    intent_logs = [r.message for r in caplog.records if r.message.startswith("[step ")]
    assert len(intent_logs) == 3
    assert intent_logs[0].startswith("[step 1]")
    assert intent_logs[1].startswith("[step 2]")
    assert intent_logs[2].startswith("[step 3]")
    for line in intent_logs:
        assert "→" in line
        assert "subgoal:" in line
        assert "map:" in line
        assert "critic:" in line