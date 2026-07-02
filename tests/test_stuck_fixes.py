"""Regression tests for WRAM alignment, stuck detection, and indoor navigation."""

from __future__ import annotations

from src.emulator.bootstrap import MAP_GROUP_ADDR, MAP_NUMBER_ADDR
from src.graph.generic_interact import (
    generic_stuck_interact_fallback,
    pocket_navigate_stuck,
)
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

    lab_gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3},
        raw_metadata={"mom_scene_complete": True},
    )
    lab_state = {"stuck_count": 5}
    _update_stuck_from_interaction(lab_state, "interact_a", lab_gs.position_key, lab_gs)
    assert lab_state["stuck_count"] == 6


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

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2, "facing": 4},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = []
    target = _navigation_target(gs, map_key=gs.map_key, state=state)
    assert target != (gs.player.x, gs.player.y)


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
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 0},
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


def test_outdoor_at_target_does_not_add_blocked_ahead_interact():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 9, "y": 12},
        raw_metadata={},
    )
    state = initial_agent_state(gs)
    target = (9, 12)
    candidates = _navigation_candidates(gs, target, [], state)
    assert "a" not in candidates


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