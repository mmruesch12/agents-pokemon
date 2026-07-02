"""House-exit and starter-quest terminal routing."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.graph import compile_graph
from src.graph.nodes import _hold_phase_satisfied, supervisor_node
from src.graph.phases import early_progression, house_exit
from src.graph.state import initial_agent_state
from src.state.models import BattleState, GameState
from tests.fake_emulator import MutableRamEmulator


def _post_house_state() -> tuple[dict, GameState]:
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 5, "map_name": "New Bark Town"},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    return state, gs


def _early_progression_satisfied_state() -> tuple[dict, GameState]:
    gs = GameState(
        player={"map_group": 1, "map_id": 2, "x": 20, "y": 20, "map_name": "Cherrygrove City"},
        party_count=1,
        raw_metadata={"has_starter": True},
        battle=BattleState(),
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    state["early_progression_complete"] = True
    return state, gs


def test_house_exit_is_satisfied_on_new_bark_exterior():
    state, gs = _post_house_state()
    assert house_exit.is_satisfied(gs, state) is True


def test_hold_phase_not_satisfied_until_starter_quest_done():
    state, gs = _post_house_state()
    assert _hold_phase_satisfied(gs, state) is False


def test_supervisor_routes_to_navigator_post_house():
    state, gs = _post_house_state()
    result = supervisor_node(state)
    assert result["next_node"] == "navigator"


def test_ten_supervisor_cycles_emit_navigate_post_house():
    state, gs = _post_house_state()
    from src.graph.nodes import critic_node, memory_node, navigator_node

    actions: list[str] = []
    for _ in range(10):
        state = supervisor_node(state)
        assert state["next_node"] == "navigator"
        state = navigator_node(state)
        actions.append(state["last_action"])
        state = critic_node(state)
        state = memory_node(state)
    assert any(a.startswith("navigate_") for a in actions)


def test_supervisor_routes_to_idle_when_early_progression_satisfied():
    state, gs = _early_progression_satisfied_state()
    result = supervisor_node(state)
    assert result["next_node"] == "idle"
    assert result["phase"] == "early_progression_done"


def test_ten_supervisor_cycles_idle_after_early_progression():
    state, gs = _early_progression_satisfied_state()
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
    assert actions == [early_progression.EARLY_PROGRESSION_DONE_ACTION] * 10
    assert not any(a.startswith("navigate_") for a in actions)


def test_graph_invoke_navigate_after_house_exit_complete():
    """Full graph: post-house state navigates toward lab, not idle."""
    from src.memory.landmarks import seed_static_map_landmarks
    from src.state.gold_state_reader import (
        ADDR_BATTLE_MODE,
        ADDR_MAP_GROUP,
        ADDR_MAP_NUMBER,
        ADDR_PARTY_COUNT,
        ADDR_X_COORD,
        ADDR_Y_COORD,
    )

    mem = {
        ADDR_MAP_GROUP: 24,
        ADDR_MAP_NUMBER: 4,
        ADDR_X_COORD: 13,
        ADDR_Y_COORD: 6,
        ADDR_PARTY_COUNT: 0,
        ADDR_BATTLE_MODE: 0,
    }
    emu = MutableRamEmulator(mem, route_29_at_x=99)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    seed_static_map_landmarks(state)
    state["run_max_steps"] = 5

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "terminal.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "terminal"}})

    assert result["metrics"]["steps"] == 5
    history = result.get("short_term_history", [])
    assert any("navigate:" in h for h in history)
    assert result["game_state"]["player"]["map_group"] == 24
    assert result["game_state"]["player"]["map_id"] == 4