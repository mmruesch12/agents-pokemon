"""Terminal house-exit: no navigation after goal satisfied on 24:4."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.graph import compile_graph
from src.graph.nodes import supervisor_node
from src.graph.phases import house_exit
from src.graph.state import initial_agent_state
from src.state.models import GameState
from tests.fake_emulator import MutableRamEmulator


def _satisfied_state() -> tuple[dict, GameState]:
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 5, "map_name": "New Bark Town"},
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    return state, gs


def test_is_satisfied_on_new_bark_exterior():
    state, gs = _satisfied_state()
    assert house_exit.is_satisfied(gs, state) is True


def test_supervisor_routes_to_idle_when_satisfied():
    state, gs = _satisfied_state()
    result = supervisor_node(state)
    assert result["next_node"] == "idle"
    assert result["phase"] == "house_exit_done"


def test_ten_supervisor_cycles_never_emit_navigate():
    state, gs = _satisfied_state()
    pos = gs.position_key
    actions: list[str] = []
    for _ in range(10):
        state = supervisor_node(state)
        assert state["next_node"] == "idle"
        from src.graph.nodes import idle_node, critic_node, memory_node

        state = idle_node(state)
        actions.append(state["last_action"])
        state = critic_node(state)
        state = memory_node(state)
        assert GameState.model_validate(state["game_state"]).position_key == pos
    assert actions == [house_exit.HOUSE_EXIT_DONE_ACTION] * 10
    assert not any(a.startswith("navigate_") for a in actions)


def test_graph_invoke_idle_after_house_exit_complete(new_bark_ram: dict):
    """Full graph: satisfied state produces only house_exit_done actions."""
    emu = MutableRamEmulator(new_bark_ram, route_29_at_x=99)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["run_max_steps"] = 5

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "terminal.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "terminal"}})

    assert result["metrics"]["steps"] == 5
    assert result["game_state"]["player"]["x"] == gs.player.x
    assert result["game_state"]["player"]["y"] == gs.player.y
    assert result["last_action"] == house_exit.HOUSE_EXIT_DONE_ACTION
    history = result.get("short_term_history", [])
    assert not any("navigate:" in h for h in history)
    assert result["game_state"]["player"]["map_group"] == 24
    assert result["game_state"]["player"]["map_id"] == 4