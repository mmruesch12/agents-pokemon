"""Unit tests for starter_quest milestone module (post Phase-2 shrink)."""

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


def test_navigation_target_delegates_to_landmarks():
    gs = _gs(24, 4, 13, 6, meta={"has_starter": False})
    assert starter_quest.navigation_target(gs) is None


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
    gs = _gs(
        24,
        3,
        10,
        5,
        meta={"has_starter": True, "has_mystery_egg": False},
        party_count=1,
    )
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
    gs_done = _gs(24, 5, 4, 6, meta={"has_starter": True}, party_count=1)
    assert starter_quest.blocked_lab_exit(gs_done) is False


def test_has_starter_requires_party_not_flag_alone():
    gs = _gs(24, 5, 3, 5, meta={"has_starter": True}, party_count=0)
    assert starter_quest.has_starter(gs) is False
    assert starter_quest.starter_flag_set(gs) is True
    subgoals = starter_quest.decompose_subgoals(gs)
    assert subgoals is not None
    assert any("Potion" in s for s in subgoals)


def test_sync_subgoals_updates_active_subgoal_in_lab():
    from src.graph.phases.starter_quest import _subgoal_index

    gs = _gs(24, 5, 4, 2, meta={"has_starter": False})
    state = {"house_exit_complete": True, "active_subgoal": "Leave player house"}
    starter_quest.sync_subgoals(gs, state)
    assert "Elm" in state["active_subgoal"]

    transit_gs = _gs(24, 5, 5, 3, meta={"has_starter": False})
    transit_state = {"house_exit_complete": True, "visited_positions": []}
    assert _subgoal_index(transit_gs, transit_state) == 0
    starter_quest.sync_subgoals(transit_gs, transit_state)
    assert "Talk to Elm" in transit_state["active_subgoal"]

    scripted_y3_gs = _gs(24, 5, 4, 3, meta={"has_starter": False})
    scripted_state = {"house_exit_complete": True, "visited_positions": ["24:5:4:3"]}
    assert _subgoal_index(scripted_y3_gs, scripted_state) == 0
    starter_quest.sync_subgoals(scripted_y3_gs, scripted_state)
    assert "Talk" in scripted_state["active_subgoal"] or "Elm" in scripted_state["active_subgoal"]

    desk_done_gs = _gs(24, 5, 4, 2, meta={"has_starter": False})
    desk_done_state = {
        "house_exit_complete": True,
        "visited_positions": ["24:5:4:2"],
    }
    assert _subgoal_index(desk_done_gs, desk_done_state) == 1
    starter_quest.sync_subgoals(desk_done_gs, desk_done_state)
    assert "Poke Ball" in desk_done_state["active_subgoal"]

    after_desk_gs = _gs(24, 5, 4, 3, meta={"has_starter": False})
    after_desk_state = {
        "house_exit_complete": True,
        "visited_positions": ["24:5:4:2"],
    }
    assert _subgoal_index(after_desk_gs, after_desk_state) == 1
    starter_quest.sync_subgoals(after_desk_gs, after_desk_state)
    assert "Poke Ball" in after_desk_state["active_subgoal"]

    from src.graph.state import initial_agent_state

    fresh = initial_agent_state()
    assert fresh.get("session_blocked") == {}
    assert fresh.get("session_walkable") == {}


def test_subgoal_index_on_route_29_after_starter():
    from src.graph.phases.starter_quest import _subgoal_index

    gs = _gs(24, 3, 59, 8, meta={"has_starter": True}, party_count=1)
    state = {"house_exit_complete": True}
    assert _subgoal_index(gs, state) == 1
    starter_quest.sync_subgoals(gs, state)
    assert state["active_subgoal"] == "Cross Route 29"


def test_ensure_house_exit_complete_on_lab_entry_from_bedroom():
    gs = _gs(24, 5, 4, 8, meta={"has_starter": False})
    state = {
        "house_exit_complete": False,
        "active_subgoal": "Leave player house",
        "maps_visited": ["24:7", "24:6", "24:4"],
    }
    starter_quest.ensure_house_exit_complete(gs, state)
    assert state["house_exit_complete"] is True
    starter_quest.sync_subgoals(gs, state)
    assert "Elm" in state["active_subgoal"]


def test_starter_milestone_entered_lab():
    gs = _gs(24, 5, 4, 8)
    maps = [MAP_KEY_NEW_BARK_TOWN, MAP_KEY_ELMS_LAB]
    assert starter_quest.starter_milestone(gs, maps) == starter_quest.MILESTONE_ENTERED_LAB


def _new_bark_ram() -> dict[int, int]:
    from src.state.gold_state_reader import (
        ADDR_BATTLE_MODE,
        ADDR_MAP_GROUP,
        ADDR_MAP_NUMBER,
        ADDR_PARTY_COUNT,
        ADDR_X_COORD,
        ADDR_Y_COORD,
    )

    return {
        ADDR_MAP_GROUP: 24,
        ADDR_MAP_NUMBER: 4,
        ADDR_X_COORD: 13,
        ADDR_Y_COORD: 6,
        ADDR_PARTY_COUNT: 0,
        ADDR_BATTLE_MODE: 0,
    }


def test_flags_from_reader_drive_metadata():
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    mem = _new_bark_ram()
    _set_flag(mem, EVENT_GOT_A_POKEMON_FROM_ELM)
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    assert gs.raw_metadata["has_starter"] is True


def test_egg_flags_from_reader():
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    mem = _new_bark_ram()
    _set_flag(mem, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)
    _set_flag(mem, EVENT_GAVE_MYSTERY_EGG_TO_ELM)
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    assert gs.raw_metadata["has_mystery_egg"] is True
    assert gs.raw_metadata["egg_delivered"] is True


def test_interior_landmark_id_follows_active_subgoal():
    from src.memory.landmarks import ELMS_LAB_BALL_APPROACH_ID, ELMS_LAB_DESK_APPROACH_ID

    desk_gs = _gs(24, 5, 4, 8, meta={"has_starter": False})
    state = {"house_exit_complete": True}
    assert starter_quest.interior_landmark_id(desk_gs, state) == ELMS_LAB_DESK_APPROACH_ID

    ball_gs = _gs(24, 5, 5, 3, meta={"has_starter": False})
    state["visited_positions"] = ["24:5:4:2"]
    assert starter_quest.interior_landmark_id(ball_gs, state) == ELMS_LAB_BALL_APPROACH_ID


def test_door_exit_direction_uses_landmark_door():
    gs = _gs(24, 4, 6, 4, meta={"has_starter": False})
    assert starter_quest.door_exit_direction(gs, door=(6, 3)) == "up"
    at_exit = _gs(24, 5, 4, 11, meta={"has_starter": True}, party_count=1)
    assert starter_quest.door_exit_direction(at_exit) == "down"