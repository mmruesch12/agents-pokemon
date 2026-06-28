"""House-exit and starter-quest terminal routing."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.graph import compile_graph
from src.graph.nodes import _hold_phase_satisfied, supervisor_node
from src.graph.phases import house_exit, starter_quest
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


def _starter_quest_satisfied_state() -> tuple[dict, GameState]:
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 8, "map_name": "Elm's Lab"},
        party_count=1,
        raw_metadata={"has_starter": True, "egg_delivered": True},
        battle=BattleState(),
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
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


def test_supervisor_routes_to_idle_when_starter_quest_satisfied():
    state, gs = _starter_quest_satisfied_state()
    result = supervisor_node(state)
    assert result["next_node"] == "idle"
    assert result["phase"] == "starter_quest_done"


def test_ten_supervisor_cycles_idle_after_starter_quest():
    state, gs = _starter_quest_satisfied_state()
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
    assert actions == [starter_quest.STARTER_QUEST_DONE_ACTION] * 10
    assert not any(a.startswith("navigate_") for a in actions)


def test_graph_invoke_navigate_after_house_exit_complete(post_house_ram: dict):
    """Full graph: post-house state navigates toward lab, not idle."""
    emu = MutableRamEmulator(post_house_ram, route_29_at_x=99)
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["run_max_steps"] = 5

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(emu, checkpoint_path=Path(tmp) / "terminal.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "terminal"}})

    assert result["metrics"]["steps"] == 5
    history = result.get("short_term_history", [])
    assert any("navigate:" in h for h in history)
    assert result["game_state"]["player"]["map_group"] == 24
    assert result["game_state"]["player"]["map_id"] == 4