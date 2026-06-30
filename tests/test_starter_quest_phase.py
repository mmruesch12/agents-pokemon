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


def test_navigation_target_elms_lab_pre_starter_targets_desk_then_ball():
    gs = _gs(24, 5, 4, 8, meta={"has_starter": False})
    assert starter_quest.navigation_target(gs) == starter_quest.ELM_DESK_TILE
    assert starter_quest.navigation_target(
        gs, state={"lab_desk_dialog_done": True}
    ) == starter_quest.STARTER_BALL_APPROACH


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
    """Elm flag set without party must not count as a full starter for milestones."""
    gs = _gs(24, 5, 3, 5, meta={"has_starter": True}, party_count=0)
    assert starter_quest.has_starter(gs) is False
    assert starter_quest.starter_flag_set(gs) is True
    assert starter_quest.navigation_target(
        gs, state={"lab_desk_dialog_done": True}
    ) == starter_quest.ELMS_LAB_EXIT
    subgoals = starter_quest.decompose_subgoals(gs)
    assert subgoals is not None
    assert any("Potion" in s for s in subgoals)


def test_starter_flag_blocks_ball_re_interact():
    gs = _gs(
        24,
        5,
        5,
        3,
        meta={"has_starter": True},
        party_count=0,
    )
    gs.player.facing = 12
    state = {"lab_desk_dialog_done": True, "stuck_count": 0}
    assert starter_quest.is_adjacent_to_starter_ball(gs) is True
    assert starter_quest.can_interact_starter_ball(gs) is False
    assert starter_quest.navigation_target(gs, state=state) == starter_quest.ELMS_LAB_EXIT
    assert starter_quest.blocked_lab_exit(gs) is False


def test_starter_pick_dialog_still_forces_interact():
    gs = _gs(
        24,
        5,
        5,
        3,
        meta={"has_starter": True, "in_script": True},
        party_count=0,
    )
    gs.in_text_box = True
    gs.player.facing = 12
    state = {"lab_desk_dialog_done": True}
    assert starter_quest.starter_pick_dialog_active(gs) is True
    assert starter_quest.lab_ball_picking_active(gs, state) is True
    assert starter_quest.needs_lab_interaction(gs, state) is True
    directive = starter_quest.resolve_lab_pre_starter(gs, state)
    assert directive is not None
    assert directive.force_interact is True


def test_far_from_ball_targets_desk_before_elm_intro():
    gs = _gs(24, 5, 4, 8, meta={"has_starter": False})
    assert starter_quest.can_interact_starter_ball(gs) is False
    assert starter_quest.navigation_target(gs) == starter_quest.ELM_DESK_TILE


def test_desk_stuck_still_forces_interact_until_intro_done():
    gs = _gs(24, 5, 4, 2, meta={"has_starter": False})
    state = {"stuck_count": 2, "last_action": "navigate_right", "lab_desk_dialog_done": False}
    assert starter_quest.needs_lab_interaction(gs, state) is True
    assert starter_quest.force_interactor(gs, state) is True


def test_ball_interact_stuck_keeps_interacting_when_facing_ball():
    gs = _gs(24, 5, 5, 3, meta={"has_starter": False}, party_count=0)
    gs.player.facing = 12
    state = {"lab_desk_dialog_done": True, "stuck_count": 2, "last_action": "interact_a"}
    assert starter_quest.ready_for_ball_interact(gs) is True
    assert starter_quest.needs_lab_interaction(gs, state) is True
    assert starter_quest.prefer_interact_candidate(gs, state) is True


def test_sync_subgoals_updates_active_subgoal_in_lab():
    gs = _gs(24, 5, 4, 2, meta={"has_starter": False})
    state = {"house_exit_complete": True, "active_subgoal": "Leave player house"}
    starter_quest.sync_subgoals(gs, state)
    assert "Elm" in state["active_subgoal"]


def test_desk_approach_does_not_complete_desk_dialog():
    gs = _gs(24, 5, 4, 3, meta={"has_starter": False})
    state: dict = {}
    starter_quest.update_lab_rom_observables(gs, state)
    assert state.get("lab_desk_dialog_done") is not True


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


def test_sync_subgoals_keeps_ball_subgoal_during_ball_dialog():
    gs = _gs(24, 5, 5, 3, meta={"has_starter": False, "in_script": True}, party_count=0)
    gs.in_text_box = True
    state = {"house_exit_complete": True, "lab_desk_dialog_done": True}
    starter_quest.sync_subgoals(gs, state)
    assert state["active_subgoal"] == "Pick a Poke Ball"


def test_ball_interact_requires_facing_and_elm_intro():
    gs = _gs(24, 5, 5, 3, meta={"has_starter": False}, party_count=0)
    gs.player.facing = 0
    state = {"lab_desk_dialog_done": True}
    assert starter_quest.ready_for_ball_interact(gs) is False
    assert starter_quest.needs_lab_interaction(gs, state) is False
    gs.player.facing = 12
    assert starter_quest.ready_for_ball_interact(gs) is True


def test_starter_milestone_entered_lab():
    gs = _gs(24, 5, 4, 8)
    maps = [MAP_KEY_NEW_BARK_TOWN, MAP_KEY_ELMS_LAB]
    assert starter_quest.starter_milestone(gs, maps) == starter_quest.MILESTONE_ENTERED_LAB


def test_flags_from_reader_drive_metadata(post_house_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    _set_flag(post_house_ram, EVENT_GOT_A_POKEMON_FROM_ELM)
    gs = GoldStateReader(ByteArrayReader(post_house_ram)).read()
    assert gs.raw_metadata["has_starter"] is True


def test_desk_dialog_done_after_script_clears():
    gs = _gs(24, 5, 4, 2, meta={"has_starter": False, "in_script": True})
    gs.in_text_box = True
    state: dict = {}
    starter_quest.update_lab_rom_observables(gs, state)
    assert state.get("lab_desk_script_seen") is True
    gs.in_text_box = False
    gs.raw_metadata = {"has_starter": False, "in_script": False}
    starter_quest.update_lab_rom_observables(gs, state)
    assert state.get("lab_desk_dialog_done") is True


def test_lab_directive_from_cli_snapshots():
    desk_gs = _gs(24, 5, 4, 2, meta={"has_starter": False})
    desk = starter_quest.resolve_lab_pre_starter(desk_gs, {})
    assert desk is not None
    assert desk.phase == starter_quest.LabPhase.DESK
    assert desk.nav_target == starter_quest.ELM_DESK_TILE
    assert desk.prefer_interact is True

    ball_gs = _gs(24, 5, 5, 3, meta={"has_starter": False}, party_count=0)
    ball_gs.player.facing = 12
    ball = starter_quest.resolve_lab_pre_starter(
        ball_gs, {"lab_desk_dialog_done": True}
    )
    assert ball is not None
    assert ball.phase == starter_quest.LabPhase.BALL_INTERACT
    assert ball.prefer_interact is True

    dialog_gs = _gs(
        24, 5, 5, 3, meta={"has_starter": False, "in_script": True}, party_count=0
    )
    dialog_gs.player.facing = 12
    dialog_gs.in_text_box = True
    wait = starter_quest.resolve_lab_pre_starter(
        dialog_gs, {"lab_desk_dialog_done": True}
    )
    assert wait is not None
    assert wait.phase == starter_quest.LabPhase.WAIT_SCRIPT
    assert wait.force_interact is True


def test_desk_approach_tile_does_not_skip_elm_intro():
    gs = _gs(24, 5, 4, 3, meta={"has_starter": False}, party_count=0)
    assert starter_quest.desk_dialog_done(gs, {}) is False
    directive = starter_quest.resolve_lab_pre_starter(gs, {})
    assert directive is not None
    assert directive.phase == starter_quest.LabPhase.DESK


def test_desk_without_script_stays_until_dialog_done():
    """Two desk interacts must not skip Elm intro when no script is running."""
    gs = _gs(24, 5, 4, 2, meta={"has_starter": False}, party_count=0)
    state = {"lab_desk_interact_count": 2}
    directive = starter_quest.resolve_lab_pre_starter(gs, state)
    assert directive is not None
    assert directive.phase == starter_quest.LabPhase.DESK
    assert directive.nav_target == starter_quest.ELM_DESK_TILE


def test_desk_dialog_pending_keeps_interacting_at_desk():
    """Active SCRIPT_READ at desk must advance dialog before ball approach."""
    gs = _gs(
        24, 5, 4, 2, meta={"has_starter": False, "in_script": True}, party_count=0
    )
    gs.in_text_box = True
    state = {"lab_desk_interact_count": 2, "lab_desk_script_seen": False}
    directive = starter_quest.resolve_lab_pre_starter(gs, state)
    assert directive is not None
    assert directive.phase == starter_quest.LabPhase.WAIT_SCRIPT
    assert directive.force_interact is True


def test_desk_dialog_done_at_desk_waits_while_script_pending():
    gs = _gs(
        24, 5, 4, 2, meta={"has_starter": False, "in_script": True}, party_count=0
    )
    gs.in_text_box = True
    directive = starter_quest.resolve_lab_pre_starter(
        gs, {"lab_desk_dialog_done": True}
    )
    assert directive is not None
    assert directive.phase == starter_quest.LabPhase.WAIT_SCRIPT
    assert directive.force_interact is True


def test_desk_dialog_done_at_ball_row_without_state_flags():
    gs = _gs(24, 5, 5, 3, meta={"has_starter": False}, party_count=0)
    assert starter_quest.desk_dialog_done(gs, {}) is True
    directive = starter_quest.resolve_lab_pre_starter(gs, {})
    assert directive is not None
    assert directive.phase in (
        starter_quest.LabPhase.BALL_INTERACT,
        starter_quest.LabPhase.BALL_APPROACH,
    )


def test_ball_face_turn_exhausted_after_repeated_navigate_right():
    gs = _gs(24, 5, 5, 3, meta={"has_starter": False}, party_count=0)
    gs.player.facing = 0
    state = {
        "lab_desk_dialog_done": True,
        "stuck_count": 2,
        "last_action": "navigate_right",
    }
    assert starter_quest.ball_face_turn_exhausted(gs, state) is True
    assert starter_quest.needs_lab_interaction(gs, state) is True


def test_lab_party_stall_not_detected_at_ball_row_during_pick():
    gs = _gs(24, 5, 5, 3, meta={"has_starter": False}, party_count=0)
    state = {
        "lab_desk_dialog_done": True,
        "lab_stall_position": gs.position_key,
        "lab_steps_without_party": 12,
        "last_action": "interact_a",
    }
    assert starter_quest.lab_ball_picking_active(gs, state) is True
    assert starter_quest.lab_party_stall_detected(gs, state) is False
    starter_quest.update_lab_rom_observables(gs, state)
    assert starter_quest.lab_party_stall_detected(gs, state) is False


def test_lab_party_stall_detected_when_approach_stalls():
    gs = _gs(24, 5, 4, 4, meta={"has_starter": False}, party_count=0)
    state = {
        "lab_desk_dialog_done": True,
        "lab_stall_position": gs.position_key,
        "lab_steps_without_party": 7,
    }
    assert starter_quest.lab_party_stall_detected(gs, state) is False
    starter_quest.update_lab_rom_observables(gs, state)
    assert starter_quest.lab_party_stall_detected(gs, state) is True


def test_egg_flags_from_reader(post_house_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    _set_flag(post_house_ram, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)
    _set_flag(post_house_ram, EVENT_GAVE_MYSTERY_EGG_TO_ELM)
    gs = GoldStateReader(ByteArrayReader(post_house_ram)).read()
    assert gs.raw_metadata["has_mystery_egg"] is True
    assert gs.raw_metadata["egg_delivered"] is True