"""Milestone emission tests for starter quest."""

from __future__ import annotations

from src.graph.nodes import _check_milestone, memory_node
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    ADDR_BATTLE_MODE,
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_ELMS_LAB,
)
from src.state.models import BattlePhase, BattleState, GameState


def test_milestone_chose_first_pokemon():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 7, "y": 3},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    milestone = _check_milestone(gs, {}, [MAP_KEY_ELMS_LAB])
    assert milestone == starter_quest.MILESTONE_CHOSE_STARTER


def test_milestone_first_rival_battle_lab_fallback():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 8},
        party_count=1,
        raw_metadata={"egg_delivered": True},
        battle=BattleState(in_battle=True, phase=BattlePhase.TRAINER),
    )
    milestone = _check_milestone(gs, {}, [MAP_KEY_ELMS_LAB])
    assert milestone == starter_quest.MILESTONE_RIVAL_BATTLE


def test_milestone_first_rival_battle_cherrygrove_before_egg_delivery():
    """Canon: rival is on Cherrygrove east edge during egg-return, before Elm."""
    gs = GameState(
        player={"map_group": 26, "map_id": 3, "x": 33, "y": 7},
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": True,
            "egg_delivered": False,
            "cherrygrove_rival_pending": True,
        },
        battle=BattleState(in_battle=True, phase=BattlePhase.TRAINER),
    )
    milestone = _check_milestone(gs, {}, [MAP_KEY_CHERRYGROVE_CITY])
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


def test_maybe_complete_after_egg_when_rival_scene_cleared():
    """FinishRival clears scene; egg delivery then hands off even if battle frame missed."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 6, "y": 7},
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": True,
            "egg_delivered": True,
            "cherrygrove_rival_pending": False,
            "cherrygrove_scene_id": 0,
        },
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["milestones"] = [starter_quest.MILESTONE_EGG_DELIVERED]
    assert starter_quest.maybe_complete_starter_quest(gs, state) is True
    assert state["starter_quest_complete"] is True


def test_maybe_complete_blocked_when_rival_still_pending():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "egg_delivered": True,
            "cherrygrove_rival_pending": True,
        },
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert starter_quest.maybe_complete_starter_quest(gs, state) is False
    assert not state.get("starter_quest_complete")


def test_route30_trainer_with_egg_is_not_first_rival():
    """Joey/Mikey on R30 must not emit First rival or complete starter quest."""
    gs = GameState(
        player={"map_group": 26, "map_id": 1, "x": 12, "y": 14},  # Route 30
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": True,
            "egg_delivered": False,
            "cherrygrove_rival_pending": True,
        },
        battle=BattleState(in_battle=True, phase=BattlePhase.TRAINER),
    )
    milestone = _check_milestone(gs, {}, ["26:1"])
    assert milestone != starter_quest.MILESTONE_RIVAL_BATTLE
    assert starter_quest._rival_battle_context(gs) is False

    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["milestones"] = []
    result = memory_node(state)
    assert starter_quest.MILESTONE_RIVAL_BATTLE not in result.get("milestones", [])
    assert not result.get("starter_quest_complete")


def test_maybe_complete_blocked_without_egg_even_with_rival_milestone():
    """Canon: rival fires before egg delivery — milestone alone must not hand off."""
    gs = GameState(
        player={"map_group": 26, "map_id": 3, "x": 33, "y": 7},
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": True,
            "egg_delivered": False,
            "cherrygrove_rival_pending": True,
        },
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["milestones"] = [starter_quest.MILESTONE_RIVAL_BATTLE]
    assert starter_quest.maybe_complete_starter_quest(gs, state) is False
    assert not state.get("starter_quest_complete")


def test_memory_node_rival_before_egg_records_milestone_only():
    """Live Cherrygrove rival before Elm: milestone yes, starter_quest_complete no."""
    gs = GameState(
        player={"map_group": 26, "map_id": 3, "x": 33, "y": 7},
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": True,
            "egg_delivered": False,
            "cherrygrove_rival_pending": True,
        },
        battle=BattleState(in_battle=True, phase=BattlePhase.TRAINER),
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = [MAP_KEY_CHERRYGROVE_CITY]
    result = memory_node(state)
    assert starter_quest.MILESTONE_RIVAL_BATTLE in result["milestones"]
    assert not result.get("starter_quest_complete")


def test_in_starter_quest_while_rival_pending_after_egg():
    """Egg delivered but FinishRival pending: stay in starter quest on Cherrygrove."""
    gs = GameState(
        player={"map_group": 26, "map_id": 3, "x": 33, "y": 7},
        party_count=1,
        raw_metadata={
            "has_starter": True,
            "egg_delivered": True,
            "cherrygrove_rival_pending": True,
        },
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert starter_quest.in_starter_quest(gs, state) is True
    assert MAP_KEY_CHERRYGROVE_CITY in starter_quest.STARTER_QUEST_MAPS