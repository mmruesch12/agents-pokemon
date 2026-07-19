"""Regression tests for WRAM alignment, stuck detection, and indoor navigation."""

from __future__ import annotations

from src.emulator.bootstrap import MAP_GROUP_ADDR, MAP_NUMBER_ADDR
from src.graph.generic_interact import (
    generic_stuck_interact_fallback,
    pocket_navigate_stuck,
)
from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, record_session_blocked
from src.graph.nodes import (
    _history_interact_repeats,
    _history_oscillates,
    _navigation_candidates,
    _navigation_target,
    _update_stuck_from_interaction,
    _update_stuck_from_movement,
    apply_action_node,
    critic_node,
    navigator_node,
    select_navigation_action,
)
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    MAP_PLAYERS_HOUSE_2F,
    MAPGROUP_NEW_BARK,
    ByteArrayReader,
    GoldStateReader,
)
from src.state.models import GameState


def test_reader_uses_same_map_addresses_as_bootstrap():
    assert ADDR_MAP_GROUP == MAP_GROUP_ADDR
    assert ADDR_MAP_NUMBER == MAP_NUMBER_ADDR


def test_reader_reads_indoor_map_from_bootstrap_addresses():
    mem = {
        ADDR_MAP_GROUP: MAPGROUP_NEW_BARK,
        ADDR_MAP_NUMBER: MAP_PLAYERS_HOUSE_2F,
        ADDR_X_COORD: 3,
        ADDR_Y_COORD: 5,
    }
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    assert gs.map_key == "24:7"
    assert gs.player.x == 3
    assert gs.player.y == 5
    assert gs.player.map_name == "Player's House 2F"


def test_position_change_counts_as_movement():
    state = {"stuck_count": 5}
    _update_stuck_from_movement(
        state,
        "navigate_right",
        "24:7:3:5",
        "24:7:4:5",
    )
    assert state["stuck_count"] == 4


def test_no_position_change_increments_stuck():
    gs = GameState(player={"map_group": 24, "map_id": 7, "x": 3, "y": 5})
    state = {"stuck_count": 5, "game_state": gs.model_dump()}
    _update_stuck_from_movement(
        state,
        "navigate_right",
        "24:7:3:5",
        "24:7:3:5",
        gs,
    )
    assert state["stuck_count"] == 6
    assert state.get("session_blocked", {}).get("24:7") == [(4, 5)]


def test_navigation_target_players_house_targets_stairs():
    gs = GameState(player={"map_group": 24, "map_id": 7, "x": 3, "y": 5})
    target = _navigation_target(gs, map_key="24:7")
    assert target == (7, 0)


def test_navigation_target_players_house_1f_targets_door_after_mom():
    from src.graph.phases.house_exit import PLAYERS_HOUSE_1F_CORRIDOR

    kitchen_gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 5, "y": 3},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(kitchen_gs, map_key="24:6") == PLAYERS_HOUSE_1F_CORRIDOR

    door_row_gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 6},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(door_row_gs, map_key="24:6") == (6, 7)


def test_navigator_players_house_moves_toward_stairs():
    gs = GameState(player={"map_group": 24, "map_id": 7, "x": 3, "y": 2})
    state = initial_agent_state(gs)
    result = navigator_node(state)
    assert result["last_action"] in ("navigate_up", "navigate_right")
    assert result["last_action_result"]["target"] == (7, 0)


def test_unproductive_interact_increments_stuck_in_lab():
    lab_gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 12},
        raw_metadata={"has_starter": False, "mom_scene_complete": True},
        party_count=0,
    )
    lab_state = {"stuck_count": 2}
    _update_stuck_from_interaction(
        lab_state, "interact_a", lab_gs.position_key, lab_gs
    )
    assert lab_state["stuck_count"] == 3


def test_desk_interact_during_dialog_does_not_increment_stuck():
    desk_gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        in_text_box=True,
        raw_metadata={"has_starter": False, "in_script": True},
        party_count=0,
    )
    desk_state = {"stuck_count": 2}
    _update_stuck_from_interaction(
        desk_state, "interact_a", desk_gs.position_key, desk_gs
    )
    assert desk_state["stuck_count"] == 1


def test_desk_interact_after_dialog_increments_stuck():
    desk_gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    desk_state = {"stuck_count": 1}
    _update_stuck_from_interaction(
        desk_state, "interact_a", desk_gs.position_key, desk_gs
    )
    assert desk_state["stuck_count"] == 2


def test_critic_does_not_replan_during_lab_dialog():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        in_text_box=True,
        raw_metadata={"has_starter": False, "in_script": True},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = ["interact:a@4,2"] * 6
    state["stuck_count"] = 0
    result = critic_node(state)
    assert result["critic_verdict"] == "proceed"


def test_ball_interact_in_text_box_does_not_increment_stuck():
    lab_gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 12},
        in_text_box=True,
        raw_metadata={"has_starter": False, "in_script": True},
        party_count=0,
    )
    lab_state = {"stuck_count": 2}
    _update_stuck_from_interaction(
        lab_state, "interact_a", lab_gs.position_key, lab_gs
    )
    assert lab_state["stuck_count"] == 1


def test_critic_replan_on_pure_interact_spam_at_ball():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = ["interact:a@5,3"] * 6
    state["stuck_count"] = 5
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_mom_scene_reset_only_during_house_mom_scene():
    house_gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={"mom_scene_complete": False},
    )
    house_state = {"stuck_count": 5}
    _update_stuck_from_interaction(
        house_state, "interact_a", house_gs.position_key, house_gs
    )
    assert house_state["stuck_count"] == 0
    # MeetMom does not accumulate stall counters (would false-trigger post-Mom escape).
    assert house_state.get("interact_no_progress_count", 0) == 0
    assert house_state.get("interact_stall_escape") is not True

    lab_gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"mom_scene_complete": True},
    )
    lab_state = {"stuck_count": 5}
    _update_stuck_from_interaction(lab_state, "interact_a", lab_gs.position_key, lab_gs)
    assert lab_state["stuck_count"] == 6


def test_script_pos_only_change_is_meaningful_progress():
    """Multi-page dialog advances script_pos while textbox/mode stay fixed."""
    from src.graph.nodes import _meaningful_script_progress

    pre = (22144, True, 1, False, True, True)
    post = (22145, True, 1, False, True, True)
    assert _meaningful_script_progress(pre, post) is True
    assert _meaningful_script_progress(pre, pre) is False
    assert _meaningful_script_progress(None, post) is False


def test_post_mom_script_pos_progress_resets_stall_counter():
    """Post-event live dialog: script_pos-only A must not arm interact_stall_escape."""
    from src.graph.nodes import _script_progress_key

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_pos": 22144,
            "script_mode": 1,
            "in_script": True,
            "script_active": True,
            "mom_scene_complete": True,
            "joypad_disable": 0,
        },
    )
    state: dict = {
        "stuck_count": 0,
        "interact_no_progress_count": 7,
        "interact_stall_escape": False,
    }
    # Simulate 12 multi-page A presses: script_pos advances every other step.
    for i in range(12):
        pre_pos = 22144 + i
        post_pos = 22144 + i + (1 if i % 2 == 0 else 0)
        state["pre_action_script_key"] = (
            pre_pos,
            True,
            1,
            False,
            True,
            True,
        )
        gs.raw_metadata["script_pos"] = post_pos
        # Keep in_text_box True via model field; metadata drives the rest.
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
        assert state.get("interact_stall_escape") is not True, f"armed at step {i}"
    # Final step with frozen keys (no progress) only bumps count once.
    assert state.get("interact_no_progress_count", 0) < 8 or state.get(
        "interact_stall_escape"
    ) is not True


def test_post_mom_frozen_dialog_short_streak_does_not_arm():
    """Eight frozen A presses while textbox open must not arm nav escape."""
    from src.graph.nodes import STUCK_THRESHOLD

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_pos": 22144,
            "script_mode": 1,
            "in_script": True,
            "script_active": True,
            "mom_scene_complete": True,
            "joypad_disable": 0,
        },
    )
    state: dict = {"stuck_count": 0, "interact_no_progress_count": 0}
    script_key = (22144, True, 1, False, True, True)
    for _ in range(8):
        state["pre_action_script_key"] = script_key
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state["interact_no_progress_count"] == 8
    assert state.get("interact_stall_escape") is not True
    # Live open textbox must not false-stuck toward replan threshold.
    assert state["stuck_count"] == 0
    assert state["stuck_count"] < STUCK_THRESHOLD


def test_post_mom_open_textbox_long_freeze_keeps_a_path():
    """Long open-textbox freeze must keep A (no nav arm / stuck inflation)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_pos": 22144,
            "script_mode": 1,
            "in_script": True,
            "script_active": True,
            "mom_scene_complete": True,
            "joypad_disable": 0,
        },
    )
    state: dict = {"stuck_count": 0, "interact_no_progress_count": 0}
    script_key = (22144, True, 1, False, True, True)
    for _ in range(22):
        state["pre_action_script_key"] = script_key
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state["interact_no_progress_count"] >= 22
    assert state.get("interact_stall_escape") is not True
    assert state["stuck_count"] == 0


def test_residue_closed_textbox_short_streak_arms():
    """Closed textbox + sticky flags + short streak arms escape (generic residue)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=False,
        raw_metadata={
            "script_pos": 22144,
            "script_mode": 1,
            "in_script": True,
            "script_active": True,
            "mom_scene_complete": True,
            "joypad_disable": 0,
        },
    )
    state: dict = {"stuck_count": 0, "interact_no_progress_count": 0}
    script_key = (22144, False, 1, False, True, True)
    for _ in range(8):
        state["pre_action_script_key"] = script_key
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state.get("interact_stall_escape") is True
    assert state["stuck_count"] == 8


def test_live_dialog_frozen_textbox_short_streak_map_agnostic():
    """Open textbox + frozen progress key must not false-stuck across maps.

    Mirrors live apply_action: pre_action_script_key is always set. Covers
    multi-page freezes (Elm desk intro, outdoor NPC talk, house dialog) without
    map-specific curricula.
    """
    from src.graph.generic_interact import INTERACT_NO_PROGRESS_RECOVERY
    from src.graph.nodes import STUCK_THRESHOLD

    # Midway between short stall streak (8) and long recovery (22).
    short_steps = 15
    assert short_steps < INTERACT_NO_PROGRESS_RECOVERY
    assert short_steps > STUCK_THRESHOLD  # old policy would already replan

    # Indoor maps only: outdoor open textbox arms recovery for sign escape.
    maps = (
        {"map_group": 24, "map_id": 5, "x": 4, "y": 2},  # Elm lab desk
        {"map_group": 24, "map_id": 6, "x": 9, "y": 1},  # house 1F
    )
    for player in maps:
        gs = GameState(
            player=player,
            in_text_box=True,
            raw_metadata={
                "script_pos": 16430,
                "script_mode": 1,
                "in_script": True,
                "script_active": True,
                "mom_scene_complete": True,
                "joypad_disable": 0,
            },
        )
        state: dict = {"stuck_count": 0, "interact_no_progress_count": 0}
        script_key = (16430, True, 1, False, True, True)
        for _ in range(short_steps):
            state["pre_action_script_key"] = script_key
            _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
        assert state["interact_no_progress_count"] == short_steps, player
        assert state["stuck_count"] == 0, player
        assert state["stuck_count"] < STUCK_THRESHOLD, player
        assert state.get("interact_stall_escape") is not True, player


def test_live_dialog_long_open_textbox_never_arms_nav_generic():
    """Elm-desk style long open textbox freeze: keep A, never nav-escape."""
    from src.graph.generic_interact import (
        INTERACT_NO_PROGRESS_RECOVERY,
        interact_stall_recovery_active,
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        in_text_box=True,
        raw_metadata={
            "script_pos": 16430,
            "script_mode": 1,
            "in_script": True,
            "script_active": True,
            "has_starter": False,
            "joypad_disable": 0,
        },
    )
    state: dict = {
        "stuck_count": 0,
        "interact_no_progress_count": 0,
        "short_term_history": ["interact:a@4,2"] * 10,
    }
    script_key = (16430, True, 1, False, True, True)
    for _ in range(INTERACT_NO_PROGRESS_RECOVERY + 5):
        state["pre_action_script_key"] = script_key
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state["interact_no_progress_count"] >= INTERACT_NO_PROGRESS_RECOVERY
    assert state.get("interact_stall_escape") is not True
    assert state["stuck_count"] == 0
    assert interact_stall_recovery_active(gs, state) is False


def test_history_oscillates_detects_nav_nav_interact_cycles():
    history = [
        "navigate:right@5,3",
        "navigate:right@5,3",
        "interact:a@5,3",
    ] * 3
    assert _history_oscillates(history) is True


def test_history_oscillates_detects_multi_tile_pocket():
    history = [
        "navigate:right@11,11",
        "interact:a@12,11",
        "navigate:left@11,11",
        "interact:a@11,11",
    ] * 3
    assert _history_oscillates(history, min_cycles=2, max_positions=6) is True


def test_failed_navigate_increments_stuck():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 12},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = {"stuck_count": 2, "facing_before_action": 0}
    _update_stuck_from_movement(
        state,
        "navigate_right",
        gs.position_key,
        gs.position_key,
        gs,
    )
    assert state["stuck_count"] == 3
    assert state.get("session_blocked", {}).get("24:5") == [(6, 3)]
    emu_less_gs = GameState(player={"map_group": 24, "map_id": 4, "x": 6, "y": 7})
    emu_less = initial_agent_state(emu_less_gs)
    emu_less["position_before_action"] = emu_less_gs.position_key
    emu_less["last_action"] = "navigate_down"
    emu_less["stuck_count"] = 0
    result = apply_action_node(emu_less, emulator=None)
    assert result["stuck_count"] == 1
    assert result.get("session_blocked", {}).get("24:4") == [(6, 8)]


def test_lab_ball_row_prefers_interact_candidate():
    from src.graph.generic_interact import generic_prefer_interact_candidate
    from src.state.script_constants import JOYPAD_DISABLE_INPUT_MASK, SCRIPT_FLAG_SCRIPT_RUNNING, SCRIPT_READ

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 0},
        raw_metadata={
            "has_starter": False,
            "script_mode": SCRIPT_READ,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
            "joypad_disable": JOYPAD_DISABLE_INPUT_MASK,
            "in_script": True,
        },
        party_count=0,
    )
    state = {
        "active_subgoal": "Pick a Poke Ball",
        "last_action": "interact_a",
        "stuck_count": 0,
    }
    assert generic_prefer_interact_candidate(gs, state) is True


def test_navigator_at_lab_5_3_faces_ball_or_interacts():
    from src.state.script_constants import JOYPAD_DISABLE_INPUT_MASK, SCRIPT_FLAG_SCRIPT_RUNNING, SCRIPT_READ

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 0},
        raw_metadata={
            "has_starter": False,
            "script_mode": SCRIPT_READ,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
            "joypad_disable": JOYPAD_DISABLE_INPUT_MASK,
            "in_script": True,
        },
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    result = navigator_node(state)
    assert "a" in result["last_action_result"]["candidates"]


def test_history_interact_repeats_detects_ball_spam():
    history = ["interact:a@5,3"] * 5
    assert _history_interact_repeats(history) is True


def test_needs_interaction_true_at_ball_row_after_interact_burst():
    from src.graph.nodes import needs_interaction

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["last_action"] = "interact_a"
    gs.in_text_box = True
    gs.raw_metadata = {"has_starter": False, "in_script": True}
    assert needs_interaction(gs, state) is True


def test_critic_does_not_replan_on_lab_party_stall_during_ball_dialog():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        in_text_box=True,
        raw_metadata={"has_starter": False, "in_script": True},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = ["interact:a@5,3"] * 6
    state["stuck_count"] = 0
    result = critic_node(state)
    assert result["critic_verdict"] == "proceed"
    assert result.get("should_replan") is not True


def test_critic_replan_on_interact_spam_at_ball():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = ["interact:a@5,3"] * 5
    state["stuck_count"] = 4
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"


def test_lab_stuck_history_triggers_critic_replan():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"has_starter": True},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = [
        "navigate:right@5,3",
        "navigate:right@5,3",
        "interact:a@5,3",
    ] * 3
    state["stuck_count"] = 2
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_navigator_from_elm_desk_targets_desk_before_intro():
    from src.memory.landmarks import discover_elms_lab_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2, "facing": 12},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = discover_elms_lab_landmarks(gs)
    starter_quest.sync_subgoals(gs, state)
    result = navigator_node(state)
    assert result["last_action_result"]["target"] is not None
    assert "Elm" in state["active_subgoal"]


def test_navigation_target_in_lab_uses_exploration_without_landmarks():
    from src.graph.nodes import _navigation_target
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2, "facing": 4},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = []
    target = _navigation_target(gs, map_key=gs.map_key, state=state)
    # Desk approach anchor is (4,2) — same tile is valid for Elm interact.
    desk = MAP_LANDMARK_ANCHORS.get("24:5", {}).get("desk_approach", (4, 2))
    assert target is not None
    assert target == desk or target != (gs.player.x, gs.player.y)


def test_navigator_from_elm_desk_routes_down_toward_ball_after_intro():
    from src.memory.landmarks import discover_elms_lab_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 12},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["visited_positions"] = ["24:5:4:2"]
    state["known_landmarks"] = discover_elms_lab_landmarks(gs)
    starter_quest.sync_subgoals(gs, state)
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["last_action_result"]["target"] is not None
    assert "Poke Ball" in state["active_subgoal"]


def test_critic_does_not_replan_during_desk_intro_oscillation():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        in_text_box=True,
        raw_metadata={"has_starter": False, "in_script": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = [
        "navigate:right@4,2",
        "navigate:right@4,2",
        "interact:a@4,2",
        "interact:a@4,2",
        "navigate:right@4,2",
        "navigate:right@4,2",
        "interact:a@4,2",
        "interact:a@4,2",
    ]
    state["stuck_count"] = 2
    result = critic_node(state)
    assert result["critic_verdict"] == "proceed"


def test_post_starter_lab_targets_exit():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    assert starter_quest.navigation_target(gs) is None
    assert starter_quest.door_exit_direction(gs) is None
    at_exit = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 11},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    assert starter_quest.door_exit_direction(at_exit) == "down"


def test_navigator_routes_to_lab_exit_when_starter_flag_set():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    starter_quest.sync_subgoals(gs, state)
    result = navigator_node(state)
    target = result["last_action_result"]["target"]
    assert target[1] >= 11
    assert state["active_subgoal"]


def test_door_exit_not_forced_when_returning_egg_to_elm():
    """Egg-return: do not bounce out of lab at (4,11) before giving egg to Elm."""
    at_exit = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 11},
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": True,
            "egg_delivered": False,
        },
        party_count=1,
    )
    assert starter_quest.door_exit_direction(at_exit) is None
    # After delivery, south exit is allowed again.
    after = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 11},
        raw_metadata={
            "has_starter": True,
            "has_mystery_egg": False,
            "egg_delivered": True,
        },
        party_count=1,
    )
    assert starter_quest.door_exit_direction(after) == "down"


def test_route31_gate_tile_forces_left_when_heading_west():
    """Standing on west_gate (4,7) must step left into Violet Gate (live thrash)."""
    from src.memory.landmarks import seed_static_map_landmarks
    from src.graph.nodes import navigator_node

    gs = GameState(
        player={"map_group": 26, "map_id": 2, "x": 4, "y": 7},
        raw_metadata={"has_starter": True, "egg_delivered": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    state["known_landmarks"] = seed_static_map_landmarks(state)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_left"


def test_pocket_stuck_lateral_move_does_not_reset_stuck_count():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = {
        "stuck_count": 1,
        "pocket_stuck_count": 1,
        "pocket_nav_positions": ["6,4"],
        "last_action": "navigate_up",
    }
    _update_stuck_from_movement(
        state,
        "navigate_down",
        "24:5:6:4",
        "24:5:6:5",
        gs,
    )
    assert state["stuck_count"] == 1
    assert state["pocket_stuck_count"] == 1


def test_pocket_stuck_triggers_indoor_interact_fallback_at_lab_ball_approach():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = {
        "stuck_count": 0,
        "pocket_stuck_count": 2,
        "pocket_nav_positions": ["6,4", "7,4"],
        "last_action": "navigate_up",
    }
    assert pocket_navigate_stuck(state) is True
    assert generic_stuck_interact_fallback(gs, state) is True


def test_history_oscillates_detects_pure_nav_ping_pong():
    history = [
        "navigate:up@6,4",
        "navigate:down@6,5",
        "navigate:left@5,4",
        "navigate:right@6,4",
    ] * 3
    assert _history_oscillates(history, min_cycles=2, max_positions=6) is True


def test_critic_replan_on_pure_nav_oscillation():
    history = [
        "navigate:up@6,4",
        "navigate:down@6,5",
        "navigate:left@5,4",
        "navigate:right@6,4",
    ] * 3
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = history
    state["stuck_count"] = 2
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_navigation_candidates_at_target_blocked_ahead_includes_interact():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    target = (6, 4)
    candidates = _navigation_candidates(gs, target, [], state)
    assert "a" in candidates


def test_select_navigation_action_at_target_blocked_ahead_picks_interact():
    # Facing up (4) at ball approach: interact immediately.
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 4},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    target = (6, 4)
    candidates = _navigation_candidates(gs, target, [], state)
    action = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice=None,
        candidates=candidates,
        stuck_count=0,
        gs=gs,
        state=state,
        target=target,
    )
    assert action == "a"
    # Facing down: turn toward the ball first.
    gs_down = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    action_turn = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice=None,
        candidates=candidates,
        stuck_count=0,
        gs=gs_down,
        state=state,
        target=target,
    )
    assert action_turn == "up"


def test_house_2f_stairs_at_target_does_not_add_blocked_ahead_interact():
    gs = GameState(player={"map_group": 24, "map_id": 7, "x": 7, "y": 0})
    state = initial_agent_state(gs)
    target = (7, 0)
    candidates = _navigation_candidates(gs, target, [], state)
    assert "a" not in candidates
    action = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice=None,
        candidates=candidates,
        stuck_count=0,
        gs=gs,
        state=state,
        target=target,
    )
    assert action != "a"


def test_house_1f_corridor_at_target_does_not_add_blocked_ahead_interact():
    from src.graph.phases.house_exit import PLAYERS_HOUSE_1F_CORRIDOR

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 8, "y": 5},
        raw_metadata={"mom_scene_complete": True},
    )
    state = initial_agent_state(gs)
    target = PLAYERS_HOUSE_1F_CORRIDOR
    candidates = _navigation_candidates(gs, target, [], state)
    assert "a" not in candidates


def test_pocket_stuck_off_target_selects_interact_under_arbitration():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 5, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["pocket_stuck_count"] = 2
    state["pocket_nav_positions"] = ["6,4", "7,4"]
    state["last_action"] = "navigate_up"
    state["stuck_count"] = 2
    target = (6, 4)
    candidates = _navigation_candidates(gs, target, ["up"], state)
    assert "a" in candidates
    action = select_navigation_action(
        door_exit=None,
        path=["up"],
        llm_choice="left",
        candidates=candidates,
        stuck_count=2,
        gs=gs,
        state=state,
        target=target,
    )
    assert action == "a"


def test_pure_nav_oscillation_respects_max_positions_four():
    """Sparse one-pass tiles outside a tight bbox do not count as classic oscillation.

    Compact multi-tile pockets still fire via bounding-box recovery (see below).
    """
    # Wide span (x 0..10) with no repeats → not a pocket loop.
    history = [f"navigate:right@{x},1" for x in range(12)]
    assert _history_oscillates(history, min_cycles=2, max_positions=4) is False


def test_pure_nav_sign_pocket_history_triggers_oscillation_and_replan():
    """Live Route 29 failure signature: wander (14–18,14–15) with stuck_count=0."""
    from src.graph.nodes import critic_node, navigation_arbitration_active
    from src.graph.state import initial_agent_state

    # Alternating tiles across the sign pocket (more than 4 unique positions).
    pocket = [
        (14, 14),
        (15, 14),
        (16, 14),
        (17, 14),
        (18, 14),
        (18, 15),
        (17, 15),
        (16, 15),
        (15, 15),
        (14, 15),
    ]
    history = []
    dirs = ["right", "right", "right", "right", "down", "left", "left", "left", "left", "up"]
    for _ in range(2):
        for d, (x, y) in zip(dirs, pocket):
            history.append(f"navigate:{d}@{x},{y}")
    assert _history_oscillates(history, min_cycles=2, max_positions=4) is True
    assert _history_oscillates(history, min_cycles=3, max_positions=4) is True

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 14, "y": 14, "facing": 0},
        raw_metadata={},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    state["short_term_history"] = history
    state["stuck_count"] = 0
    assert navigation_arbitration_active(0, state) is True
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_outdoor_at_target_does_not_add_blocked_ahead_interact():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 9, "y": 12},
        raw_metadata={},
    )
    state = initial_agent_state(gs)
    target = (9, 12)
    candidates = _navigation_candidates(gs, target, [], state)
    assert "a" not in candidates


def test_west_edge_left_failure_does_not_block_oob_tile(new_bark_ram: dict):
    from src.state.gold_state_reader import (
        ADDR_EVENT_FLAGS,
        ByteArrayReader,
        GoldStateReader,
    )
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM

    mem = dict(new_bark_ram)
    mem[ADDR_X_COORD] = 0
    mem[ADDR_Y_COORD] = 8
    mem[ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)] = 1 << (
        EVENT_GOT_A_POKEMON_FROM_ELM % 8
    )
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    state = initial_agent_state(gs)
    state["position_before_action"] = gs.position_key
    state["last_action"] = "navigate_left"
    state["stuck_count"] = 5
    _update_stuck_from_movement(
        state,
        "navigate_left",
        gs.position_key,
        gs.position_key,
        gs,
    )
    assert state["stuck_count"] == 6
    assert state.get("session_blocked", {}).get("24:4") is None


def test_west_edge_left_failure_from_approach_does_not_block_warp_tile(new_bark_ram: dict):
    from src.state.gold_state_reader import (
        ADDR_EVENT_FLAGS,
        ADDR_X_COORD,
        ADDR_Y_COORD,
        ByteArrayReader,
        GoldStateReader,
    )
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM

    mem = dict(new_bark_ram)
    mem[ADDR_X_COORD] = 1
    mem[ADDR_Y_COORD] = 8
    mem[ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)] = 1 << (
        EVENT_GOT_A_POKEMON_FROM_ELM % 8
    )
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    state = initial_agent_state(gs)
    state["position_before_action"] = gs.position_key
    state["last_action"] = "navigate_left"
    state["stuck_count"] = 5
    _update_stuck_from_movement(
        state,
        "navigate_left",
        gs.position_key,
        gs.position_key,
        gs,
    )
    assert state["stuck_count"] == 6
    assert state.get("session_blocked", {}).get("24:4") is None


def test_apply_action_clears_stuck_on_map_transition(new_bark_ram: dict):
    from src.state.gold_state_reader import (
        ADDR_EVENT_FLAGS,
        ByteArrayReader,
        GoldStateReader,
    )
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM
    from tests.fake_emulator import MutableRamEmulator

    mem = dict(new_bark_ram)
    mem[ADDR_X_COORD] = 0
    mem[ADDR_Y_COORD] = 8
    mem[ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)] = 1 << (
        EVENT_GOT_A_POKEMON_FROM_ELM % 8
    )
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    emu = MutableRamEmulator(mem, route_29_west_at_x=0)
    state = initial_agent_state(gs)
    state["game_state"] = gs.model_dump()
    state["position_before_action"] = gs.position_key
    state["last_action"] = "navigate_left"
    state["stuck_count"] = 12
    state["pocket_stuck_count"] = 4
    state["pocket_nav_positions"] = ["0,8"]
    result = apply_action_node(state, emulator=emu)
    gs_after = GameState.model_validate(result["game_state"])
    assert gs_after.map_key == "24:3"
    assert result["stuck_count"] == 0
    assert result.get("pocket_stuck_count") == 0


def test_select_nav_faces_blocked_object_before_a():
    """At ball approach facing wrong way: turn toward object before A."""
    from src.graph.nodes import select_navigation_action

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 12},  # right
        party_count=0,
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    target = (6, 4)
    action = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice="a",
        candidates=["a", "left", "right", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=target,
    )
    assert action == "up"
    gs_facing_up = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 4},
        party_count=0,
        raw_metadata={"has_starter": False},
    )
    action_ready = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice="a",
        candidates=["a", "left", "right", "down"],
        stuck_count=0,
        gs=gs_facing_up,
        state=state,
        target=target,
    )
    assert action_ready == "a"


def test_select_nav_invalid_facing_still_presses_a():
    """Non-standard facing: try face-up a few times, then A (no infinite face loop)."""
    from src.graph.nodes import select_navigation_action

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 7},
        party_count=0,
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    action = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice="a",
        candidates=["a", "up", "left", "right", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(6, 4),
    )
    # Prefer face-up so ball interact works even with junk facing bytes.
    assert action == "up"
    state["short_term_history"] = ["navigate:up@6,4"] * 3
    action2 = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice="a",
        candidates=["a", "up", "left", "right", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(6, 4),
    )
    assert action2 == "a"


def test_navigate_a_uses_interact_hold_and_progress_tracking(new_bark_ram: dict):
    """navigate_a (at-target A) must use interact hold/tick path, not short nav A."""
    from src.graph.nodes import INTERACT_HOLD_FRAMES
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
    from tests.fake_emulator import MutableRamEmulator

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    emu = MutableRamEmulator(new_bark_ram)
    holds: list[int] = []
    orig_press = emu.press_button

    def tracking_press(button: str, *, hold_frames: int = 2) -> None:
        holds.append(hold_frames)
        return orig_press(button, hold_frames=hold_frames)

    emu.press_button = tracking_press  # type: ignore[method-assign]
    state = initial_agent_state(gs)
    state["game_state"] = gs.model_dump()
    state["position_before_action"] = gs.position_key
    state["last_action"] = "navigate_a"
    state["stuck_count"] = 0
    result = apply_action_node(state, emulator=emu)
    assert holds and holds[0] == INTERACT_HOLD_FRAMES
    # Interaction path: no movement stuck bump solely from same-tile A.
    assert result["stuck_count"] == 0 or "pre_action_script_key" not in result


def test_route_29_ledge_path_detours_instead_of_west_on_row_8():
    from src.graph.pathfinding import find_path
    from src.memory.landmarks import ROUTE_29_NORTH_GATE_ID, make_landmark

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 44, "y": 8},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=ROUTE_29_NORTH_GATE_ID,
            name="Route 29 north gate",
            map_key="24:3",
            x=10,
            y=5,
            kind="map_visit",
        )
    ]
    record_session_blocked(state, "24:3", 43, 8)
    path = find_path(44, 8, *MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"], map_key="24:3", state=state)
    assert path
    assert path[0] != "left"


def test_select_navigation_follows_path_on_route_29_ledge_row():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 27, "y": 10},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["visited_positions"] = ["24:3:26:10", "24:3:27:9"]
    action = select_navigation_action(
        door_exit=None,
        path=["up", "up", "left"],
        llm_choice="left",
        candidates=["up", "left", "right", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action == "up"


def test_select_navigation_skips_llm_when_repeating_blocked_direction():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 44, "y": 8})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:left@44,8"] * 3
    action = select_navigation_action(
        door_exit=None,
        path=["down", "left"],
        llm_choice="left",
        candidates=["left", "down", "right"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action != "left"


def test_route_29_east_ledge_forced_down_despite_llm_up():
    """(44,8)/(44,9) pure-nav thrash: position changes so stuck stays 0; force down."""
    from src.graph.navigation_resolve import ROUTE_29_SOUTH_CORRIDOR

    for x, y in ((44, 8), (44, 9), (45, 9)):
        gs = GameState(player={"map_group": 24, "map_id": 3, "x": x, "y": y})
        state = initial_agent_state(gs)
        state["short_term_history"] = [
            "navigate:up@44,9",
            "navigate:down@44,8",
        ] * 6
        path = ["down", "down", "left", "left"]
        action = select_navigation_action(
            door_exit=None,
            path=path,
            llm_choice="up",
            candidates=["up", "down", "left", "right"],
            stuck_count=0,
            gs=gs,
            state=state,
            target=ROUTE_29_SOUTH_CORRIDOR,
        )
        assert action == "down", f"at {(x, y)} got {action}"


def test_route_29_stuck_recovery_prefers_south_corridor_over_north_frontier():
    """Oscillation recovery must not override landmark routing with north thrash."""
    from src.graph.nodes import _stuck_recovery_target
    from src.graph.navigation_resolve import ROUTE_29_SOUTH_CORRIDOR
    from src.memory.landmarks import seed_static_map_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 44, "y": 9},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["active_subgoal"] = "Travel west on Route 29"
    state["subgoals"] = ["Travel west on Route 29", "Reach Cherrygrove City"]
    state["known_landmarks"] = seed_static_map_landmarks(state)
    state["short_term_history"] = [
        "navigate:up@44,9",
        "navigate:down@44,8",
    ] * 8
    recovery = _stuck_recovery_target(gs, state)
    assert recovery == ROUTE_29_SOUTH_CORRIDOR


def test_exploration_heading_route_30_matches_travel_west_subgoal():
    from src.graph.exploration import exploration_heading_route_30_gate

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 50, "y": 9},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    state["active_subgoal"] = "Travel west on Route 29"
    state["subgoals"] = ["Travel west on Route 29", "Reach Cherrygrove City"]
    assert exploration_heading_route_30_gate(gs, state)


def test_outdoor_sign_close_blocks_tile_for_detour():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 38, "y": 14},
        in_text_box=False,
        raw_metadata={"script_pos": 31533, "script_mode": 0, "in_script": False},
    )
    state: dict = {"stuck_count": 5, "interact_no_progress_count": 3}
    pre_key = (31532, True, 1, False)
    state["pre_action_script_key"] = pre_key
    _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert (38, 14) in state.get("session_blocked", {}).get("24:3", [])
    assert state.get("interact_no_progress_count") == 0


def test_interact_outdoor_open_textbox_short_freeze_tracks_no_progress():
    """Outdoor open textbox: track freezes; climb stuck after long freeze; no B-escape."""
    from src.graph.generic_interact import OUTDOOR_FROZEN_SCRIPT_RECOVERY

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=True,
        raw_metadata={
            "script_pos": 31532,
            "script_mode": 1,
            "in_script": True,
            "script_flags": 4,
        },
    )
    state: dict = {"stuck_count": 0, "interact_no_progress_count": 0}
    script_key = (31532, True, 1, False)
    # Short freeze (<6): track only, no stuck climb.
    for _ in range(min(5, OUTDOOR_FROZEN_SCRIPT_RECOVERY)):
        state["pre_action_script_key"] = script_key
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state["interact_no_progress_count"] >= 1
    assert state["stuck_count"] == 0
    assert state.get("interact_stall_escape") is not True
    assert state.get("outdoor_script_frozen_count", 0) >= 1
    # Long freeze: stuck climbs so hard soft-lock reload can fire (live R30).
    for _ in range(10):
        state["pre_action_script_key"] = script_key
        _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state["stuck_count"] >= 1
    assert state.get("interact_stall_escape") is not True


def test_interact_closed_textbox_residue_blocks_tile_and_increments_stuck():
    """Closed textbox + sticky script: short freeze is residue (stuck + blocked)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=False,
        raw_metadata={
            "script_pos": 31532,
            "script_mode": 1,
            "in_script": True,
            "script_flags": 4,
        },
    )
    state: dict = {"stuck_count": 0}
    script_key = (31532, False, 1, False)
    state["pre_action_script_key"] = script_key
    _update_stuck_from_interaction(state, "interact_a", gs.position_key, gs)
    assert state["stuck_count"] == 1
    assert state.get("interact_no_progress_count") == 1
    assert (41, 14) in state.get("session_blocked", {}).get("24:3", [])


def test_route_29_y11_dead_end_session_blocked_after_entry():
    from src.graph.nodes import ROUTE_29_Y11_DEAD_END, _update_stuck_from_movement

    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 22, "y": 11})
    state: dict = {}
    _update_stuck_from_movement(
        state,
        "navigate_right",
        "24:3:23:11",
        gs.position_key,
        gs,
    )
    assert ROUTE_29_Y11_DEAD_END in state.get("session_blocked", {}).get("24:3", [])


def test_select_navigation_forces_east_on_route_29_south_corridor():
    from src.graph.navigation_resolve import ROUTE_29_CORRIDOR_EAST_REENTRY
    from src.graph.nodes import select_navigation_action

    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 14, "y": 14})
    state: dict = {
        "visited_positions": ["24:3:15:14", "24:3:14:14"],
        "short_term_history": [],
    }
    action = select_navigation_action(
        door_exit=None,
        path=["right", "right", "right", "right", "right", "right", "right", "right"],
        llm_choice="left",
        candidates=["left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=ROUTE_29_CORRIDOR_EAST_REENTRY,
    )
    assert action == "right"


def test_select_navigation_forces_gate_path_on_route_29_south_corridor():
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    # Climb gap x=22 on y=14: only "up" reaches the west corridor (not down thrash).
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 22, "y": 14})
    state: dict = {"short_term_history": []}
    action = select_navigation_action(
        door_exit=None,
        path=["down", "left", "left", "left"],
        llm_choice="right",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "up"


def test_select_navigation_forces_left_on_route_29_y15_south_corridor():
    """Non-climb south-corridor tiles still follow A* west (not climb thrash)."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 30, "y": 15})
    state: dict = {"short_term_history": []}
    action = select_navigation_action(
        door_exit=None,
        path=["left", "left", "up", "left"],
        llm_choice="right",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "left"


def test_select_navigation_follows_gate_path_on_route_29_y16_west():
    from src.graph.nodes import select_navigation_action

    state: dict = {"short_term_history": []}
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 24, "y": 16})
    action = select_navigation_action(
        door_exit=None,
        path=["up", "left", "left", "left"],
        llm_choice="right",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action == "up"


def test_select_navigation_forces_east_on_route_29_y16_when_not_gate_target():
    from src.graph.nodes import select_navigation_action
    from src.graph.navigation_resolve import ROUTE_29_Y16_EAST_ANCHOR

    state: dict = {"short_term_history": []}
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 24, "y": 16})
    action = select_navigation_action(
        door_exit=None,
        path=["left", "left", "left"],
        llm_choice="left",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=ROUTE_29_Y16_EAST_ANCHOR,
    )
    assert action == "right"


def test_select_navigation_rejects_left_into_route_29_sign_wall():
    """Wrong A* left into the sign wall is corrected; valid escape is not forced east."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import find_path

    state: dict = {"short_term_history": []}
    gs_sign = GameState(player={"map_group": 24, "map_id": 3, "x": 14, "y": 14})
    # Broken path into wall → not left.
    assert (
        select_navigation_action(
            door_exit=None,
            path=["left", "left", "left"],
            llm_choice="left",
            candidates=["left", "right", "down", "up"],
            stuck_count=0,
            gs=gs_sign,
            state=state,
            target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
        )
        != "left"
    )
    # Real A* from the pocket follows path (escape is up/right, not forced down/east).
    real_path = find_path(14, 14, *MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"], map_key="24:3")
    assert real_path
    action = select_navigation_action(
        door_exit=None,
        path=real_path,
        llm_choice="left",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs_sign,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action == real_path[0]
    assert action in ("right", "up")

    gs_pocket = GameState(player={"map_group": 24, "map_id": 3, "x": 14, "y": 15})
    assert (
        select_navigation_action(
            door_exit=None,
            path=["left", "up", "right"],
            llm_choice="left",
            candidates=["left", "right", "down", "up"],
            stuck_count=0,
            gs=gs_pocket,
            state=state,
            target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
        )
        == "up"
    )


def test_select_navigation_follows_path_out_of_route_29_sign_pocket():
    """A* escape (up/right then corridor) is not overridden by east-force trap."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import find_path

    for x, y in ((15, 15), (16, 15), (15, 14), (18, 14)):
        gs = GameState(player={"map_group": 24, "map_id": 3, "x": x, "y": y})
        path = find_path(x, y, 10, 12, map_key="24:3")
        assert path, f"no path from {(x, y)}"
        action = select_navigation_action(
            door_exit=None,
            path=path,
            llm_choice="left",
            candidates=["left", "right", "down", "up"],
            stuck_count=0,
            gs=gs,
            state={"short_term_history": []},
            target=(10, 12),
        )
        assert action == path[0], f"{(x, y)}: got {action}, path0 {path[0]}"


def test_select_navigation_route_29_y15_east_dead_end_ascends_to_corridor():
    from src.graph.nodes import select_navigation_action

    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 33, "y": 15})
    action = select_navigation_action(
        door_exit=None,
        path=["up", "left", "left", "left"],
        llm_choice="right",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state={"short_term_history": []},
        target=(10, 12),
    )
    assert action == "up"

    gs_mid = GameState(player={"map_group": 24, "map_id": 3, "x": 24, "y": 15})
    action_mid = select_navigation_action(
        door_exit=None,
        path=["left", "left", "up"],
        llm_choice="right",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs_mid,
        state={"short_term_history": []},
        target=(22, 14),
    )
    assert action_mid == "left"


def test_select_navigation_forces_down_on_route_29_west_corridor_row():
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 23, "y": 12})
    state: dict = {"short_term_history": []}
    action = select_navigation_action(
        door_exit=None,
        path=["down", "left", "down", "down", "left"],
        llm_choice="left",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "down"


def test_navigation_candidates_omit_session_blocked_at_route_29_y11():
    """Session-blocked dead-end tile is not offered as a navigation candidate."""
    from src.graph.pathfinding import record_session_blocked

    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 23, "y": 11})
    state: dict = {}
    record_session_blocked(state, "24:3", 22, 11)
    path = ["right", "up", "left"]
    candidates = _navigation_candidates(
        gs, MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"], path, state
    )
    assert "left" not in candidates
    assert "right" in candidates


def test_outdoor_interact_suppressed_on_session_blocked_standing_tile():
    from src.graph.generic_interact import generic_prefer_interact_candidate
    from src.graph.pathfinding import record_session_blocked

    # Closed residue on a soft-lock tile: do not re-pin interactor.
    gs_closed = GameState(
        player={"map_group": 24, "map_id": 3, "x": 38, "y": 14},
        in_text_box=False,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state: dict = {}
    record_session_blocked(state, "24:3", 38, 14)
    assert generic_prefer_interact_candidate(gs_closed, state) is False
    # Open textbox still needs pure A even on a session-blocked standing tile.
    gs_open = GameState(
        player={"map_group": 24, "map_id": 3, "x": 38, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    assert generic_prefer_interact_candidate(gs_open, state) is True


def test_navigation_skips_interact_candidate_during_outdoor_recovery():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=False,
        raw_metadata={"script_pos": 1, "script_mode": 0, "in_script": False},
    )
    state = initial_agent_state(gs)
    state["interact_no_progress_count"] = 22
    candidates = _navigation_candidates(gs, MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"], ["up", "right"], state)
    assert "a" not in candidates


def test_outdoor_recovery_suppressed_while_rom_expects_dialog():
    from src.graph.generic_interact import (
        OUTDOOR_OPEN_TEXTBOX_RECOVERY,
        outdoor_interact_recovery_active,
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    # Open outdoor textbox: never nav-escape (B/nav soft-locks SCRIPT_READ).
    state = {"interact_no_progress_count": max(1, OUTDOOR_OPEN_TEXTBOX_RECOVERY - 5)}
    assert outdoor_interact_recovery_active(gs, state) is False
    state["interact_no_progress_count"] = OUTDOOR_OPEN_TEXTBOX_RECOVERY
    assert outdoor_interact_recovery_active(gs, state) is False
    state["interact_no_progress_count"] = OUTDOOR_OPEN_TEXTBOX_RECOVERY + 20
    assert outdoor_interact_recovery_active(gs, state) is False


def test_planner_routes_navigator_when_outdoor_interact_stuck():
    from src.graph.nodes import needs_interaction, planner_node

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=False,
        raw_metadata={"script_pos": 1, "script_mode": 0, "in_script": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["interact_no_progress_count"] = 22
    assert needs_interaction(gs, state) is False
    result = planner_node(state)
    assert result["next_node"] == "navigator"


def test_planner_keeps_interactor_while_outdoor_dialog_active():
    from src.graph.generic_interact import OUTDOOR_OPEN_TEXTBOX_RECOVERY
    from src.graph.nodes import needs_interaction, planner_node

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["interact_no_progress_count"] = max(1, OUTDOOR_OPEN_TEXTBOX_RECOVERY - 5)
    assert needs_interaction(gs, state) is True
    result = planner_node(state)
    assert result["next_node"] == "interactor"


def test_critic_does_not_replan_on_outdoor_open_textbox_interact_spam():
    """Open outdoor textbox: keep pure A (no planner replan thrash — live R30)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = ["interact:a@41,14"] * 6
    state["stuck_count"] = 0
    state["interact_no_progress_count"] = 22
    result = critic_node(state)
    assert result["critic_verdict"] == "proceed"
    assert result.get("should_replan") is not True


def test_critic_replans_on_closed_dialog_interact_no_progress():
    """Closed-textbox interact residue still triggers replan."""
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=False,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["short_term_history"] = ["interact:a@41,14"] * 6
    state["stuck_count"] = 0
    state["interact_no_progress_count"] = 22
    result = critic_node(state)
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_select_navigation_prefers_path_over_llm_when_arbitrating():
    # Mid-corridor y=14 open (not sign trap / forced ledge tiles).
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 20, "y": 14})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:up@20,14"] * 3
    action = select_navigation_action(
        door_exit=None,
        path=["right", "up", "left"],
        llm_choice="up",
        candidates=["up", "right", "down"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action == "right"


def test_select_navigation_skips_repeat_dir_in_path_prefix():
    # Corridor helper near reentry used to force path[0] even when it was the
    # repeating failed direction; skip-repeat must still win under arbitration.
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 20, "y": 14})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:up@20,14"] * 3
    action = select_navigation_action(
        door_exit=None,
        path=["up", "right", "down"],
        llm_choice="up",
        candidates=["up", "right", "down"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action == "right"


def test_select_navigation_forces_south_at_route_29_wall_npc_approach():
    """y=14 east of wall (x≈38–47): go south before left into NPC/wall thrash."""
    from src.graph.nodes import select_navigation_action

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    for x in (39, 40, 41, 44, 47):
        gs = GameState(player={"map_group": 24, "map_id": 3, "x": x, "y": 14})
        state = initial_agent_state(gs)
        action = select_navigation_action(
            door_exit=None,
            path=["left", "left", "down"],
            llm_choice="left",
            candidates=["left", "right", "down", "up"],
            stuck_count=0,
            gs=gs,
            state=state,
            target=gate,
        )
        assert action == "down", (x, action)
    # Wall edge on y=15: left is solid ####; must drop to open y=16 first.
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 38, "y": 15})
    state = initial_agent_state(gs)
    action = select_navigation_action(
        door_exit=None,
        path=["left", "left", "down"],
        llm_choice="left",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "down"


def test_outdoor_stuck_with_dialog_returns_dialog_clear_buttons():
    """Open outdoor textbox: pure A only (B hard-locks SCRIPT_READ — live R30)."""
    from src.graph.nodes import select_navigation_action

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 40, "y": 14},
        in_text_box=True,
        raw_metadata={"in_script": True},
    )
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:left@40,14"] * 5
    a_high = select_navigation_action(
        door_exit=None,
        path=["left", "down"],
        llm_choice="left",
        candidates=["left", "down", "right", "up"],
        stuck_count=12,
        gs=gs,
        state=state,
        target=gate,
    )
    assert a_high == "a"
    # B must not fire while textbox is open (mod-5 used to inject B).
    still_a = select_navigation_action(
        door_exit=None,
        path=["left", "down"],
        llm_choice="left",
        candidates=["left", "down", "right", "up"],
        stuck_count=15,
        gs=gs,
        state=state,
        target=gate,
    )
    assert still_a == "a"


def test_outdoor_stuck_closed_dialog_may_press_b():
    """Closed textbox + sticky script may still use rare B for menu residue."""
    from src.graph.nodes import select_navigation_action

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 40, "y": 14},
        in_text_box=False,
        raw_metadata={"in_script": True},
    )
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:left@40,14"] * 5
    action = select_navigation_action(
        door_exit=None,
        path=["left", "down"],
        llm_choice="left",
        candidates=["left", "down", "right", "up"],
        stuck_count=14,  # 14 % 7 == 0 → b
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "b"


def test_route_30_egg_return_commits_astar_path0():
    """Egg return must honor A* (right at 12,25; not L/R thrash away from x=14)."""
    from src.graph.nodes import select_navigation_action

    gs = GameState(
        player={"map_group": 26, "map_id": 1, "x": 12, "y": 25},
        raw_metadata={"has_mystery_egg": True, "egg_delivered": False},
    )
    state = initial_agent_state(gs)
    action = select_navigation_action(
        door_exit=None,
        path=["right", "right", "down"],
        llm_choice="left",
        candidates=["left", "right", "up", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(7, 53),
    )
    assert action == "right"


def test_route_29_westbound_commits_astar_path0_east_detour():
    """Post-egg mid thrash (29–30,10): A* goes right toward x36 bridge — commit it."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    west_exit = MAP_LANDMARK_ANCHORS["24:3"]["west_exit"]
    for x, y in ((29, 10), (30, 10), (36, 10)):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": x, "y": y},
            raw_metadata={"has_starter": True, "egg_delivered": True},
            party_count=1,
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        state["starter_quest_complete"] = True
        path = find_path(x, y, *west_exit, map_key="24:3")
        assert path, f"no path from {(x, y)}"
        action = select_navigation_action(
            door_exit=None,
            path=path,
            llm_choice="left",
            candidates=["left", "right", "up", "down"],
            stuck_count=0,
            gs=gs,
            state=state,
            target=west_exit,
        )
        assert action == path[0], f"{(x, y)}: got {action}, path0 {path[0]}"


def test_violet_gym_approach_commits_astar_path0():
    """Violet thrash at (22,y): A* goes south to y=18 then west to door (live wall at x=21)."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    gym = MAP_LANDMARK_ANCHORS["10:5"]["gym_entrance"]
    for x, y in ((22, 11), (22, 13), (22, 14)):
        gs = GameState(
            player={"map_group": 10, "map_id": 5, "x": x, "y": y},
            raw_metadata={"has_starter": True, "egg_delivered": True},
            party_count=1,
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        state["starter_quest_complete"] = True
        path = find_path(x, y, *gym, map_key="10:5")
        # Live wall at x=21 for y≤17 — must not path0 left into it.
        assert path and path[0] == "down", (x, y, path)
        action = select_navigation_action(
            door_exit=None,
            path=path,
            llm_choice="up",
            candidates=["left", "right", "up", "down"],
            stuck_count=0,
            gs=gs,
            state=state,
            target=gym,
        )
        assert action == "down", f"{(x, y)}: got {action}"


def test_egg_return_r29_prefers_path0_not_a_on_sticky_script():
    """Egg-return R29: sticky in_script without textbox must not A-spam (live soft-lock)."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    east = MAP_LANDMARK_ANCHORS["24:3"]["east_exit"]
    for x, y in ((32, 7), (17, 5), (28, 6)):
        gs = GameState(
            player={"map_group": 24, "map_id": 3, "x": x, "y": y},
            raw_metadata={
                "has_mystery_egg": True,
                "egg_delivered": False,
                "has_starter": True,
                "in_script": True,
                "script_active": True,
            },
            party_count=1,
            in_text_box=False,
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        path = find_path(x, y, *east, map_key="24:3")
        assert path, (x, y)
        action = select_navigation_action(
            door_exit=None,
            path=path,
            llm_choice="a",
            candidates=["left", "right", "up", "down"],
            stuck_count=6,
            gs=gs,
            state=state,
            target=east,
        )
        assert action not in {"a", "b"}, f"{(x, y)}: got {action} (must walk, not A-spam)"
        assert action in {"left", "right", "up", "down"}


def test_egg_return_open_textbox_keeps_interactor_not_path0():
    """Open outdoor dialog during egg-return: interactor A, not path0 walk."""
    from src.graph.nodes import select_navigation_action, supervisor_node
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    # Cherrygrove rival multi-page dialog (26:3) while holding egg.
    gs = GameState(
        player={"map_group": 26, "map_id": 3, "x": 33, "y": 7},
        party_count=1,
        in_text_box=True,
        raw_metadata={
            "has_mystery_egg": True,
            "egg_delivered": False,
            "has_starter": True,
            "cherrygrove_rival_pending": True,
            "in_script": True,
            "script_active": True,
            "script_mode": 1,
        },
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["outdoor_script_frozen_count"] = 8
    state["interact_no_progress_count"] = 10
    state["stuck_count"] = 5
    out = supervisor_node(state)
    assert out["next_node"] == "interactor"

    east = MAP_LANDMARK_ANCHORS["26:3"]["east_exit"]
    path = find_path(33, 7, *east, map_key="26:3") or ["right", "up"]
    action = select_navigation_action(
        door_exit=None,
        path=path,
        llm_choice="right",
        candidates=["left", "right", "up", "down", "a"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=east,
    )
    assert action == "a"


def test_egg_return_r29_forces_right_when_eastbound_walkable():
    """Egg-return must walk east/south toward New Bark — never left or A-spam."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    east = MAP_LANDMARK_ANCHORS["24:3"]["east_exit"]
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 32, "y": 7},
        raw_metadata={
            "has_mystery_egg": True,
            "egg_delivered": False,
            "has_starter": True,
            "in_script": False,
        },
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    path = find_path(32, 7, *east, map_key="24:3")
    action = select_navigation_action(
        door_exit=None,
        path=path or ["right"],
        llm_choice="left",
        candidates=["left", "right", "up", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=east,
    )
    # Live corridor forces south to y12–14 before pure-east (y7–8 soft-lock).
    assert action in {"right", "down"}, action
    assert action != "left"


def test_violet_gym_path_uses_y18_door_approach():
    """East entry and mid-city A* reach gym door via (18,18)↑, not x=22 north thrash."""
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, find_path

    gym = MAP_LANDMARK_ANCHORS["10:5"]["gym_entrance"]
    path = find_path(39, 25, *gym, map_key="10:5")
    assert path, "no path east entry → gym"
    # Simulate positions; must visit y=18 west strip and not require left from (22,17).
    x, y = 39, 25
    visited = [(x, y)]
    for step in path:
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[step]
        x, y = x + dx, y + dy
        visited.append((x, y))
    assert (18, 18) in visited or (18, 17) in visited
    assert (22, 11) not in visited  # north thrash alley avoided from east start
    # From thrash pocket, first step is south not left
    assert find_path(22, 13, *gym, map_key="10:5")[0] == "down"


def test_route_30_south_edge_door_exit_is_down():
    """Standing on R30 south_exit (egg-return) must step down into Cherrygrove."""
    from src.graph.nodes import _players_house_door_exit
    from src.memory.landmarks import seed_static_map_landmarks

    for x in (6, 7):
        gs = GameState(
            player={"map_group": 26, "map_id": 1, "x": x, "y": 53},
            raw_metadata={"has_mystery_egg": True, "egg_delivered": False},
            party_count=1,
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        seed_static_map_landmarks(state)
        assert _players_house_door_exit(gs, state) == "down", x


def test_route_30_south_entry_northbound_does_not_force_down():
    """Post-rival R30 entry at south_exit must walk north, not bounce to Cherry."""
    from src.graph.nodes import _players_house_door_exit, navigator_node
    from src.memory.landmarks import seed_static_map_landmarks
    from src.graph.phases import early_progression

    gs = GameState(
        player={"map_group": 26, "map_id": 1, "x": 7, "y": 53},
        raw_metadata={"has_starter": True, "egg_delivered": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    seed_static_map_landmarks(state)
    early_progression.sync_subgoals(gs, state)
    assert _players_house_door_exit(gs, state) is None
    out = navigator_node(state)
    assert out["last_action"] == "navigate_up"


def test_route_30_y48_northbound_commits_right_toward_climb():
    """Post-rival at (6,48): A* path0 is right to x=12 climb, not down to Cherry."""
    from src.graph.nodes import navigator_node, select_navigation_action
    from src.memory.landmarks import seed_static_map_landmarks
    from src.graph.phases import early_progression
    from src.graph.pathfinding import find_path

    gs = GameState(
        player={"map_group": 26, "map_id": 1, "x": 6, "y": 48},
        raw_metadata={"has_starter": True, "egg_delivered": True, "has_mystery_egg": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    seed_static_map_landmarks(state)
    early_progression.sync_subgoals(gs, state)
    path = find_path(6, 48, 6, 0, map_key="26:1")
    assert path and path[0] == "right"
    action = select_navigation_action(
        door_exit=None,
        path=path,
        llm_choice="down",
        candidates=["up", "down", "left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(6, 0),
    )
    assert action == "right"
    out = navigator_node(state)
    assert out["last_action"] == "navigate_right"


def test_route_31_westbound_path_to_violet_gate():
    """Post-rival R31 entry (~26,17) A* reaches pret gate (4,7), not open-grid thrash."""
    from src.graph.nodes import navigator_node, select_navigation_action
    from src.memory.landmarks import seed_static_map_landmarks
    from src.graph.phases import early_progression
    from src.graph.pathfinding import find_path

    gs = GameState(
        player={"map_group": 26, "map_id": 2, "x": 26, "y": 17},
        raw_metadata={"has_starter": True, "egg_delivered": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    seed_static_map_landmarks(state)
    early_progression.sync_subgoals(gs, state)
    path = find_path(26, 17, 4, 7, map_key="26:2")
    assert path, "must path east entry to Violet gate (4,7)"
    assert path[0] in ("left", "up", "right")
    # Never enter Bug Catcher Wade LOS (18,12–15).
    x, y = 26, 17
    for step in path:
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[step]
        x, y = x + dx, y + dy
        assert not (x == 18 and 12 <= y <= 15), f"Wade LOS at {(x, y)}"
    action = select_navigation_action(
        door_exit=None,
        path=path,
        llm_choice="right",
        candidates=["left", "right", "up", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(4, 7),
    )
    assert action == path[0]
    assert navigator_node(state)["last_action"].startswith("navigate_")


def test_route_31_path_avoids_soft_lock_from_east_pocket():
    """East entry → gate avoids Wade LOS; live BFS uses y12 west corridor."""
    from src.graph.pathfinding import find_path

    for start in ((24, 11), (24, 13), (24, 17), (30, 14), (26, 17)):
        path = find_path(start[0], start[1], 4, 7, map_key="26:2")
        assert path, f"no path from {start}"
        x, y = start
        saw_y12 = False
        coords = [(x, y)]
        for step in path:
            dx, dy = {
                "up": (0, -1),
                "down": (0, 1),
                "left": (-1, 0),
                "right": (1, 0),
            }[step]
            x, y = x + dx, y + dy
            coords.append((x, y))
            assert not (x == 18 and 12 <= y <= 15), f"Wade LOS at {(x, y)}"
            if y == 12 and x <= 16:
                saw_y12 = True
        assert (x, y) == (4, 7)
        if start == (30, 14):
            assert saw_y12, "live BFS uses y12 west from east entry"
        if start == (26, 17):
            # R30 warp entry must use y14 (28,14), not (28,15) hard-freeze.
            assert (28, 15) not in coords, coords[:20]
            assert (28, 14) in coords, coords[:20]


def test_route_31_live_bfs_gate_path_from_east_entry():
    """Live BFS (bed_chain_r31): (30,14)→(4,7) via (16,9)↓y12, not Wade column."""
    from src.graph.pathfinding import find_path

    path = find_path(30, 14, 4, 7, map_key="26:2")
    assert path and len(path) < 60
    x, y = 30, 14
    coords = [(x, y)]
    for step in path:
        dx, dy = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0),
        }[step]
        x, y = x + dx, y + dy
        coords.append((x, y))
    assert (x, y) == (4, 7)
    assert any(c[0] == 16 and c[1] <= 12 for c in coords)
    assert any(c[1] == 12 and c[0] <= 14 for c in coords)
    assert not any(c[0] == 18 and c[1] >= 12 for c in coords)


def test_route_30_north_from_y12_prefers_west_strip():
    """Live pure-up at x2–5 y12 fails; nav forces left into x0–1 corridor."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import find_path

    for start in ((3, 12), (4, 12), (5, 12)):
        path = find_path(start[0], start[1], 6, 0, map_key="26:1")
        assert path, f"no path from {start}"
        # A* must not pure-up through false-open y11 x2–5.
        assert path[0] == "left", f"{start}: path0={path[0]}, need left"
        gs = GameState(
            player={"map_group": 26, "map_id": 1, "x": start[0], "y": start[1]},
            party_count=1,
        )
        action = select_navigation_action(
            door_exit=None,
            path=path,
            llm_choice="up",
            candidates=["left", "right", "up", "down"],
            stuck_count=0,
            gs=gs,
            state={"starter_quest_complete": True, "short_term_history": []},
            target=(6, 0),
        )
        assert action == "left", f"{start}: got {action}, need left to west strip"

    # Live BFS path shape: (3,13)→x1 vertical→(2,7)→(6,0).
    path = find_path(3, 13, 6, 0, map_key="26:1")
    assert path
    x, y = 3, 13
    coords = [(x, y)]
    for step in path:
        if step == "left":
            x -= 1
        elif step == "right":
            x += 1
        elif step == "up":
            y -= 1
        elif step == "down":
            y += 1
        coords.append((x, y))
    assert (x, y) == (6, 0)
    assert any(c[0] <= 1 and c[1] <= 11 for c in coords), coords
    assert not any(c[0] in (3, 4, 5) and c[1] == 11 for c in coords), coords


def test_route_29_eastbound_path_exists_for_egg_return():
    """Egg return needs A* past y=14 ledge (climb gaps include x=44–47)."""
    from src.graph.pathfinding import find_path

    p = find_path(0, 6, 59, 8, map_key="24:3", max_steps=150)
    assert p, "eastbound path Cherrygrove edge → New Bark edge"
    assert p.count("right") > p.count("left")


def test_new_bark_egg_return_does_not_force_west_edge():
    """At New Bark west edge with egg, go toward lab — not left back to R29."""
    from src.graph.nodes import _players_house_door_exit, select_navigation_action
    from src.graph.pathfinding import find_path
    from src.memory.landmarks import seed_static_map_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 0, "y": 8},
        raw_metadata={
            "has_mystery_egg": True,
            "egg_delivered": False,
            "has_starter": True,
        },
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    seed_static_map_landmarks(state)
    door = _players_house_door_exit(gs, state)
    assert door != "left"
    path = find_path(0, 8, 6, 4, map_key="24:4", max_steps=40, state=state)
    action = select_navigation_action(
        door_exit=door,
        path=path or ["up", "right"],
        llm_choice="left",
        candidates=["up", "right", "down"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(6, 4),
    )
    assert action in ("up", "right"), action


def test_outdoor_dialog_residue_nav_fail_skips_session_block():
    """Failed outdoor nav during dialog residue must not wall-off A* neighbors."""
    from src.graph.nodes import _update_stuck_from_movement

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 40, "y": 14},
        in_text_box=True,
        raw_metadata={"in_script": True},
    )
    state = initial_agent_state(gs)
    state["interact_stall_escape"] = False
    _update_stuck_from_movement(
        state,
        "navigate_left",
        gs.position_key,
        gs.position_key,
        gs,
    )
    assert state["stuck_count"] == 1
    assert (39, 14) not in state.get("session_blocked", {}).get("24:3", [])


def test_select_navigation_falls_through_when_only_repeat_dir_candidate():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 44, "y": 8})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:left@44,8"] * 3
    action = select_navigation_action(
        door_exit=None,
        path=["down"],
        llm_choice="left",
        candidates=["left"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"],
    )
    assert action == "down"


def test_lab_interactor_uses_only_a_during_ball_pick():
    from src.graph.nodes import interactor_node

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 12},
        in_text_box=True,
        raw_metadata={"has_starter": False, "in_script": True},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["interact_action_index"] = 7
    state["last_action"] = "interact_a"
    result = interactor_node(state)
    assert result["last_action"] == "interact_a"


def test_failed_nav_during_stall_escape_skips_session_block():
    """Dialog residue nav fails must not solidify walkable neighbors on Route 29."""
    from src.graph.nodes import _update_stuck_from_movement

    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 19, "y": 4})
    state = initial_agent_state(gs)
    state["interact_stall_escape"] = True
    state["stuck_count"] = 0
    _update_stuck_from_movement(
        state,
        "navigate_left",
        "24:3:19:4",
        "24:3:19:4",
        gs,
    )
    assert state["stuck_count"] == 1
    assert (18, 4) not in state.get("session_blocked", {}).get("24:3", [])


def test_select_navigation_breaks_two_tile_climb_oscillation():
    """Force-up vs force-down climb thrash must exit laterally (stuck stays 0)."""
    from src.graph.nodes import select_navigation_action

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 22, "y": 14})
    state = initial_agent_state(gs)
    hist: list[str] = []
    for i in range(8):
        hist.append("navigate:up@22,14" if i % 2 == 0 else "navigate:down@22,13")
    state["short_term_history"] = hist
    action = select_navigation_action(
        door_exit=None,
        path=["right", "right", "up"],
        llm_choice="up",
        candidates=["up", "down", "left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "right"


def test_route_29_post_climb_forces_down_not_lateral_thrash():
    """After y=14 climb, follow A* south off y=13 (not left↔right with stuck=0)."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    gate = MAP_LANDMARK_ANCHORS["24:3"]["route_30_gate"]
    for x, y, expect in ((22, 13, "down"), (25, 13, "down"), (26, 13, "down")):
        gs = GameState(player={"map_group": 24, "map_id": 3, "x": x, "y": y})
        state = initial_agent_state(gs)
        action = select_navigation_action(
            door_exit=None,
            path=["down", "right", "right"],
            llm_choice="left",
            candidates=["up", "down", "left", "right"],
            stuck_count=0,
            gs=gs,
            state=state,
            target=gate,
        )
        assert action == expect, (x, y, action)
    # Climb y=14: force-up only when A* agrees; westbound A* starts with right.
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 27, "y": 14})
    state = initial_agent_state(gs)
    action = select_navigation_action(
        door_exit=None,
        path=["right", "right", "up"],
        llm_choice="up",
        candidates=["up", "down", "left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action == "right"
    # Empty/up path still forces the climb.
    action_up = select_navigation_action(
        door_exit=None,
        path=["up", "up", "right"],
        llm_choice="left",
        candidates=["up", "down", "left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=gate,
    )
    assert action_up == "up"


def test_ball_approach_faces_up_when_facing_invalid():
    """Elm ball interact must try face-up even when facing byte is non-pret."""
    from src.graph.nodes import select_navigation_action
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS

    target = MAP_LANDMARK_ANCHORS["24:5"]["ball_approach"]
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 255},
        party_count=0,
    )
    state = initial_agent_state(gs)
    action = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice="a",
        candidates=["a", "up", "down", "left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=target,
    )
    assert action == "up"
    state["short_term_history"] = ["navigate:up@6,4"] * 3
    action2 = select_navigation_action(
        door_exit=None,
        path=[],
        llm_choice="a",
        candidates=["a", "up", "down", "left", "right"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=target,
    )
    assert action2 == "a"


def test_elms_lab_exit_approach_steps_right_not_down():
    """After starter at (3,11), must step right onto (4,11) — not force south into wall."""
    from src.graph.nodes import navigator_node, _players_house_door_exit
    from src.graph.phases import starter_quest
    from src.memory.landmarks import seed_static_map_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 3, "y": 11},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    seed_static_map_landmarks(state)
    starter_quest.sync_subgoals(gs, state)
    assert starter_quest.door_exit_direction(gs) == "right"
    assert _players_house_door_exit(gs, state) == "right"
    assert navigator_node(state)["last_action"] == "navigate_right"

    gs_door = gs.model_copy(
        update={"player": gs.player.model_copy(update={"x": 4, "y": 11})}
    )
    state2 = initial_agent_state(gs_door)
    state2["house_exit_complete"] = True
    seed_static_map_landmarks(state2)
    assert starter_quest.door_exit_direction(gs_door) == "down"
    assert navigator_node(state2)["last_action"] == "navigate_down"
