"""Verification plan step 2: shipped nodes on synthetic post-house/lab/battle states."""

from __future__ import annotations

from src.graph.nodes import (
    _hold_phase_satisfied,
    _navigation_target,
    apply_action_node,
    memory_node,
    navigator_node,
    planner_node,
    supervisor_node,
)
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state, update_game_state
from src.state.gold_state_reader import (
    ADDR_BATTLE_MODE,
    ADDR_EVENT_FLAGS,
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_PARTY_COUNT,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    ByteArrayReader,
    GoldStateReader,
)
from src.state.models import BattlePhase, BattleState, GameState
from src.state.script_constants import EVENT_GAVE_MYSTERY_EGG_TO_ELM
from tests.fake_emulator import StarterQuestEmulator


def _post_house_gs() -> GameState:
    return GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
        party_count=0,
    )


def _post_house_memory() -> dict[int, int]:
    return {
        ADDR_MAP_GROUP: 24,
        ADDR_MAP_NUMBER: 4,
        ADDR_X_COORD: 13,
        ADDR_Y_COORD: 6,
        ADDR_PARTY_COUNT: 0,
        ADDR_BATTLE_MODE: 0,
    }


def test_verification_post_house_navigates_to_lab_warp():
    from src.memory.landmarks import seed_static_map_landmarks

    gs = _post_house_gs()
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    seed_static_map_landmarks(state)
    assert _navigation_target(gs, state=state) == (6, 4)
    assert _hold_phase_satisfied(gs, state) is False
    sup = supervisor_node(state)
    assert sup["next_node"] == "navigator"


def test_verification_lab_state_chose_first_pokemon_milestone():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 7, "y": 3},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = ["24:4", "24:5"]
    state = memory_node(state)
    assert starter_quest.MILESTONE_CHOSE_STARTER in state["milestones"]


def test_verification_trainer_battle_rival_milestone_and_satisfied(battle_ram: dict):
    mem = dict(battle_ram)
    mem[ADDR_BATTLE_MODE] = 2
    flag_addr = ADDR_EVENT_FLAGS + (EVENT_GAVE_MYSTERY_EGG_TO_ELM // 8)
    mem[flag_addr] = mem.get(flag_addr, 0) | (1 << (EVENT_GAVE_MYSTERY_EGG_TO_ELM % 8))
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    gs = gs.model_copy(
        update={
            "player": gs.player.model_copy(update={"map_group": 24, "map_id": 5, "x": 4, "y": 2}),
            "battle": BattleState(in_battle=True, phase=BattlePhase.TRAINER),
        }
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = ["24:4", "24:5"]
    assert starter_quest.is_satisfied(gs, state) is False
    state = memory_node(state)
    assert starter_quest.MILESTONE_RIVAL_BATTLE in state["milestones"]
    assert state["starter_quest_complete"] is True
    gs_after = GameState.model_validate(state["game_state"])
    assert starter_quest.is_satisfied(gs_after, state) is True
    assert _hold_phase_satisfied(gs_after, state) is False
    assert supervisor_node(state)["next_node"] == "battler"


def test_verification_supervisor_battler_before_complete_flag(battle_ram: dict):
    mem = dict(battle_ram)
    mem[ADDR_BATTLE_MODE] = 2
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert starter_quest.is_satisfied(gs, state) is False
    assert supervisor_node(state)["next_node"] == "battler"


def test_verification_shipped_apply_progression_emits_rival():
    gs = _post_house_gs()
    emu = StarterQuestEmulator(_post_house_memory())
    from src.memory.landmarks import seed_static_map_landmarks

    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["maps_visited"] = ["24:4"]
    seed_static_map_landmarks(state)

    for _ in range(800):
        state = supervisor_node(state)
        node = state["next_node"]
        if node == "navigator":
            state = navigator_node(state)
        elif node == "interactor":
            from src.graph.nodes import interactor_node

            state = interactor_node(state)
        elif node == "planner":
            state = planner_node(state)
        elif node == "waiter":
            from src.graph.nodes import waiter_node

            state = waiter_node(state)
        elif node == "battler":
            from src.graph.nodes import battler_node

            state = battler_node(state)
        state = apply_action_node(state, emu)
        state = update_game_state(state, emu.get_game_state())
        from src.graph.nodes import critic_node

        state = critic_node(state)
        state = memory_node(state)
        if starter_quest.MILESTONE_RIVAL_BATTLE in state.get("milestones", []):
            break

    gs = GameState.model_validate(state["game_state"])
    assert starter_quest.MILESTONE_CHOSE_STARTER in state["milestones"]
    assert starter_quest.MILESTONE_MR_POKEMON in state["milestones"]
    assert gs.raw_metadata.get("has_mystery_egg") is True