"""Unit tests for starter_quest phase module."""

from __future__ import annotations

from src.graph.phases import starter_quest
from src.state.gold_state_reader import (
    ADDR_EVENT_FLAGS,
    MAP_KEY_ELMS_LAB,
    MAP_KEY_NEW_BARK_TOWN,
)
from src.state.models import BattlePhase, BattleState, GameState
from src.state.script_constants import (
    EVENT_GAVE_MYSTERY_EGG_TO_ELM,
    EVENT_GOT_A_POKEMON_FROM_ELM,
    EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON,
)


def _set_flag(mem: dict[int, int], flag_index: int) -> None:
    byte_addr = ADDR_EVENT_FLAGS + (flag_index // 8)
    bit = flag_index % 8
    mem[byte_addr] = mem.get(byte_addr, 0) | (1 << bit)


def _gs(
    group: int,
    map_id: int,
    x: int,
    y: int,
    *,
    meta: dict | None = None,
    party_count: int = 0,
    battle: BattleState | None = None,
) -> GameState:
    return GameState(
        player={
            "map_group": group,
            "map_id": map_id,
            "x": x,
            "y": y,
            "map_name": f"map_{group}_{map_id}",
        },
        party_count=party_count,
        raw_metadata=meta or {},
        battle=battle or BattleState(),
    )


def test_navigation_target_new_bark_targets_lab_warp():
    gs = _gs(24, 4, 13, 6, meta={"has_starter": False})
    assert starter_quest.navigation_target(gs) == starter_quest.NEW_BARK_LAB_WARP


def test_navigation_target_elms_lab_pre_starter_targets_ball():
    gs = _gs(24, 5, 4, 8, meta={"has_starter": False})
    assert starter_quest.navigation_target(gs) == starter_quest.STARTER_BALL_TILE


def test_is_satisfied_false_before_rival_battle():
    gs = _gs(24, 5, 4, 2, meta={"egg_delivered": True})
    state = {"house_exit_complete": True}
    assert starter_quest.is_satisfied(gs, state) is False


def test_is_satisfied_true_only_with_complete_flag():
    battle = BattleState(in_battle=True, phase=BattlePhase.TRAINER)
    gs = _gs(
        24,
        5,
        4,
        8,
        meta={"egg_delivered": True},
        party_count=1,
        battle=battle,
    )
    assert starter_quest.is_satisfied(gs, {"house_exit_complete": True}) is False
    assert (
        starter_quest.is_satisfied(
            gs, {"house_exit_complete": True, "starter_quest_complete": True}
        )
        is True
    )


def test_decompose_subgoals_egg_quest_stage():
    gs = _gs(24, 3, 10, 5, meta={"has_starter": True, "has_mystery_egg": False})
    subgoals = starter_quest.decompose_subgoals(gs)
    assert subgoals is not None
    assert any("Mr. Pokemon" in s for s in subgoals)


def test_decompose_subgoals_lab_interior():
    gs = _gs(24, 5, 4, 8, meta={"has_starter": False})
    subgoals = starter_quest.decompose_subgoals(gs)
    assert subgoals is not None
    assert any("Poke Ball" in s for s in subgoals)


def test_in_starter_quest_active_post_house():
    gs = _gs(24, 4, 13, 6, meta={"has_starter": False})
    state = {"house_exit_complete": True}
    assert starter_quest.in_starter_quest(gs, state) is True


def test_blocked_lab_exit_pre_starter():
    gs = _gs(24, 5, 4, 6, meta={"has_starter": False})
    assert starter_quest.blocked_lab_exit(gs) is True
    gs_done = _gs(24, 5, 4, 6, meta={"has_starter": True})
    assert starter_quest.blocked_lab_exit(gs_done) is False


def test_starter_milestone_entered_lab():
    gs = _gs(24, 5, 4, 8)
    maps = [MAP_KEY_NEW_BARK_TOWN, MAP_KEY_ELMS_LAB]
    assert starter_quest.starter_milestone(gs, maps) == starter_quest.MILESTONE_ENTERED_LAB


def test_flags_from_reader_drive_metadata(post_house_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    _set_flag(post_house_ram, EVENT_GOT_A_POKEMON_FROM_ELM)
    gs = GoldStateReader(ByteArrayReader(post_house_ram)).read()
    assert gs.raw_metadata["has_starter"] is True


def test_egg_flags_from_reader(post_house_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    _set_flag(post_house_ram, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)
    _set_flag(post_house_ram, EVENT_GAVE_MYSTERY_EGG_TO_ELM)
    gs = GoldStateReader(ByteArrayReader(post_house_ram)).read()
    assert gs.raw_metadata["has_mystery_egg"] is True
    assert gs.raw_metadata["egg_delivered"] is True