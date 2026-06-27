"""Full graph.invoke cycles with MutableRamEmulator driving apply_action."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.graph import compile_graph
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from tests.fake_emulator import MutableRamEmulator


def test_full_graph_progression_low_stuck(new_bark_ram: dict):
    """10-step full cycle: coords evolve, stuck stays low, visited grows."""
    emu = MutableRamEmulator(new_bark_ram, route_29_at_x=99)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["run_max_steps"] = 10

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "progress.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "progress"}})

    assert result["metrics"]["steps"] == 10
    assert result["stuck_count"] < 3
    assert result["game_state"]["player"]["x"] == 18
    assert len(result["visited_positions"]) == 10


def test_full_graph_single_step_updates_position(new_bark_ram: dict):
    emu = MutableRamEmulator(new_bark_ram)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["run_max_steps"] = 1

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "one.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "one"}})

    assert result["metrics"]["steps"] == 1
    assert result["last_action"] == "navigate_right"
    assert result["game_state"]["player"]["x"] == 9
    assert result["stuck_count"] == 0
    assert result["visited_positions"] == ["0:0:9:12"]


def test_full_graph_milestone_on_map_transition(new_bark_ram: dict):
    """Moving east triggers map transition and Route 29 milestone."""
    emu = MutableRamEmulator(new_bark_ram, route_29_at_x=12)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["run_max_steps"] = 5

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "milestone.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "milestone"}})

    assert "Reached Route 29" in result["milestones"]
    assert result["game_state"]["player"]["map_group"] == 1


def test_stuck_increments_on_failed_movement(new_bark_ram: dict):
    """Blocked right movement increments stuck; successful move decrements."""
    from src.graph.nodes import apply_action_node, navigator_node

    mem = dict(new_bark_ram)
    mem_blocked = MutableRamEmulator(mem)

    class BlockedEmulator(MutableRamEmulator):
        def press_button(self, button: str, *, hold_frames: int = 2) -> None:
            if button == "right":
                self._frame_count += hold_frames + 1
                return
            super().press_button(button, hold_frames=hold_frames)

    emu = BlockedEmulator(new_bark_ram)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state = navigator_node(state)
    state = apply_action_node(state, emu)
    assert state["stuck_count"] == 1
    assert state["game_state"]["player"]["x"] == 8

    state = navigator_node(state)
    state = apply_action_node(state, emu)
    assert state["stuck_count"] == 2


def test_navigator_records_candidates(new_bark_ram: dict):
    from src.graph.nodes import navigator_node

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    result = navigator_node(state)
    assert "right" in result["last_action_result"]["candidates"]