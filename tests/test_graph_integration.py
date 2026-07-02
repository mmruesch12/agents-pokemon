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
    emu = MutableRamEmulator(new_bark_ram, route_29_west_at_x=-1)
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
    assert result["visited_positions"] == ["24:4:9:12"]


def test_full_graph_milestone_on_map_transition(new_bark_ram: dict):
    """Moving west on the Route 29 row triggers map transition and milestone."""
    from src.state.gold_state_reader import ADDR_EVENT_FLAGS, ADDR_X_COORD, ADDR_Y_COORD
    from src.memory.landmarks import seed_static_map_landmarks
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM

    mem = dict(new_bark_ram)
    mem[ADDR_X_COORD] = 3
    mem[ADDR_Y_COORD] = 8
    flag_byte = ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)
    mem[flag_byte] = mem.get(flag_byte, 0) | (1 << (EVENT_GOT_A_POKEMON_FROM_ELM % 8))
    emu = MutableRamEmulator(mem)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    seed_static_map_landmarks(state)
    state["run_max_steps"] = 10

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "milestone.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "milestone"}})

    assert "Reached Route 29" in result["milestones"]
    assert result["game_state"]["player"]["map_group"] == 24
    assert result["game_state"]["player"]["map_id"] == 3


def test_stuck_increments_on_failed_movement(new_bark_ram: dict):
    """Blocked right movement increments stuck; successful move decrements."""
    from src.graph.nodes import apply_action_node, navigator_node

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