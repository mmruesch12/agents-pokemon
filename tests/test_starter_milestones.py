"""Milestone emission tests for starter quest."""

from __future__ import annotations

from src.graph.nodes import _check_milestone, memory_node
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ADDR_BATTLE_MODE, MAP_KEY_ELMS_LAB
from src.state.models import BattlePhase, BattleState, GameState


def test_milestone_chose_first_pokemon():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 7, "y": 3},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    milestone = _check_milestone(gs, {}, [MAP_KEY_ELMS_LAB])
    assert milestone == starter_quest.MILESTONE_CHOSE_STARTER


def test_milestone_first_rival_battle():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 8},
        party_count=1,
        raw_metadata={"egg_delivered": True},
        battle=BattleState(in_battle=True, phase=BattlePhase.TRAINER),
    )
    milestone = _check_milestone(gs, {}, [MAP_KEY_ELMS_LAB])
    assert milestone == starter_quest.MILESTONE_RIVAL_BATTLE


def test_memory_node_sets_starter_quest_complete_on_rival(battle_ram: dict):
    from src.state.gold_state_reader import ADDR_EVENT_FLAGS, ByteArrayReader, GoldStateReader
    from src.state.script_constants import EVENT_GAVE_MYSTERY_EGG_TO_ELM

    battle_ram[ADDR_BATTLE_MODE] = 2
    flag_addr = ADDR_EVENT_FLAGS + (EVENT_GAVE_MYSTERY_EGG_TO_ELM // 8)
    battle_ram[flag_addr] = battle_ram.get(flag_addr, 0) | (
        1 << (EVENT_GAVE_MYSTERY_EGG_TO_ELM % 8)
    )
    gs = GoldStateReader(ByteArrayReader(battle_ram)).read()
    gs = gs.model_copy(
        update={
            "player": gs.player.model_copy(update={"map_group": 24, "map_id": 5}),
            "battle": BattleState(in_battle=True, phase=BattlePhase.TRAINER),
        }
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    result = memory_node(state)
    assert starter_quest.MILESTONE_RIVAL_BATTLE in result["milestones"]
    assert result["starter_quest_complete"] is True