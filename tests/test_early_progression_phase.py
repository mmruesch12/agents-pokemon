"""Unit tests for post-rival early_progression phase (shipped functions only)."""

from __future__ import annotations

from src.graph.nodes import (
    _decompose_subgoals,
    _hold_phase_satisfied,
    _navigation_target,
    idle_node,
    supervisor_node,
)
from src.graph.phases import early_progression, starter_quest
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
)
from src.state.models import BattlePhase, BattleState, GameState


def _state(
    gs: GameState,
    *,
    starter_complete: bool = True,
    early_complete: bool = False,
) -> dict:
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = starter_complete
    state["early_progression_complete"] = early_complete
    return state


def test_hold_false_post_rival_on_route_maps():
    for map_key, group, map_id in (
        (MAP_KEY_NEW_BARK_TOWN, 24, 4),
        (MAP_KEY_ROUTE_29, 24, 3),
        (MAP_KEY_ROUTE_30, 26, 1),
    ):
        gs = GameState(
            player={"map_group": group, "map_id": map_id, "x": 10, "y": 12},
            party_count=1,
            raw_metadata={"has_starter": True},
        )
        state = _state(gs)
        assert starter_quest.is_satisfied(gs, state) is True
        assert early_progression.is_satisfied(gs, state) is False
        assert _hold_phase_satisfied(gs, state) is False


def test_hold_true_at_cherrygrove_terminal():
    gs = GameState(
        player={"map_group": 1, "map_id": 2, "x": 20, "y": 20},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = _state(gs)
    assert early_progression.is_satisfied(gs, state) is True
    assert _hold_phase_satisfied(gs, state) is True
    assert supervisor_node(state)["next_node"] == "idle"
    assert supervisor_node(state)["phase"] == "early_progression_done"


def test_supervisor_routes_battler_during_rival_not_idle():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        party_count=1,
        raw_metadata={"has_starter": True, "egg_delivered": True},
        battle=BattleState(in_battle=True, phase=BattlePhase.TRAINER),
    )
    state = _state(gs)
    assert _hold_phase_satisfied(gs, state) is False
    assert supervisor_node(state)["next_node"] == "battler"


def test_decompose_subgoals_post_rival_contain_route_cherrygrove():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = _state(gs)
    subgoals = _decompose_subgoals(gs, state)
    assert any("Route 29" in s for s in subgoals)
    assert any("Cherrygrove" in s for s in subgoals)


def test_navigation_target_route_29_moves_northward():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = _state(gs)
    target = _navigation_target(gs, state=state)
    assert target[1] < gs.player.y


def test_navigation_target_new_bark_eastward_post_rival():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = _state(gs)
    target = _navigation_target(gs, state=state)
    assert target[0] > gs.player.x


def test_supervisor_navigator_post_rival_route_29():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = _state(gs)
    assert supervisor_node(state)["next_node"] == "navigator"


def test_memory_milestone_sets_early_progression_complete():
    from src.graph.nodes import memory_node

    gs = GameState(
        player={"map_group": 1, "map_id": 2, "x": 20, "y": 20},
        party_count=1,
    )
    state = _state(gs)
    state["maps_visited"] = [MAP_KEY_CHERRYGROVE_CITY]
    state = memory_node(state)
    assert early_progression.MILESTONE_REACHED_CHERRYGROVE in state["milestones"]
    assert state["early_progression_complete"] is True


def test_post_rival_emulator_reaches_route_29_east(new_bark_ram: dict):
    """Shipped nodes navigate east on New Bark after rival without idle lock."""
    from src.state.gold_state_reader import ADDR_EVENT_FLAGS
    from src.state.script_constants import (
        EVENT_GAVE_MYSTERY_EGG_TO_ELM,
        EVENT_GOT_A_POKEMON_FROM_ELM,
    )
    from tests.fake_emulator import MutableRamEmulator

    mem = dict(new_bark_ram)
    for flag in (EVENT_GOT_A_POKEMON_FROM_ELM, EVENT_GAVE_MYSTERY_EGG_TO_ELM):
        byte = ADDR_EVENT_FLAGS + (flag // 8)
        mem[byte] = mem.get(byte, 0) | (1 << (flag % 8))
    emu = MutableRamEmulator(mem, route_29_at_x=15)
    gs = emu.get_game_state()
    state = _state(gs)
    actions: list[str] = []
    for _ in range(12):
        sup = supervisor_node(state)
        assert sup["next_node"] != "idle"
        if sup["next_node"] == "navigator":
            from src.graph.nodes import apply_action_node, critic_node, memory_node, navigator_node

            state = navigator_node(state)
            actions.append(state["last_action"])
            state = apply_action_node(state, emu)
            from src.graph.state import update_game_state

            state = update_game_state(state, emu.get_game_state())
            state = critic_node(state)
            state = memory_node(state)
        else:
            break
    gs_after = emu.get_game_state()
    assert any(a.startswith("navigate_") for a in actions)
    assert gs_after.player.x >= 13 or gs_after.map_key == MAP_KEY_ROUTE_29


def test_idle_node_early_progression_done_action():
    gs = GameState(
        player={"map_group": 1, "map_id": 2, "x": 20, "y": 20},
        party_count=1,
    )
    state = _state(gs, early_complete=True)
    result = idle_node(state)
    assert result["last_action"] == early_progression.EARLY_PROGRESSION_DONE_ACTION