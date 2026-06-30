"""Regression tests for WRAM alignment, stuck detection, and indoor navigation."""

from __future__ import annotations

from src.emulator.bootstrap import MAP_GROUP_ADDR, MAP_NUMBER_ADDR
from src.graph.nodes import (
    _history_interact_repeats,
    _history_oscillates,
    _navigation_target,
    _update_stuck_from_interaction,
    _update_stuck_from_movement,
    critic_node,
    navigator_node,
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
    state = {"stuck_count": 5}
    _update_stuck_from_movement(
        state,
        "navigate_right",
        "24:7:3:5",
        "24:7:3:5",
    )
    assert state["stuck_count"] == 6


def test_navigation_target_players_house_targets_stairs():
    gs = GameState(player={"map_group": 24, "map_id": 7, "x": 3, "y": 5})
    target = _navigation_target(gs, map_key="24:7")
    assert target == (7, 0)


def test_navigation_target_players_house_1f_targets_door_after_mom():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 5, "y": 3},
        raw_metadata={"mom_scene_complete": True},
    )
    target = _navigation_target(gs, map_key="24:6")
    assert target == (6, 7)


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
    lab_state = {"stuck_count": 2, "lab_desk_dialog_done": True}
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
    state["lab_desk_dialog_done"] = True
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


def test_macro_steps_from_lab_ball_row_gain_party(post_house_ram: dict):
    from src.graph.nodes import (
        apply_action_node,
        critic_node,
        interactor_node,
        memory_node,
        supervisor_node,
    )
    from src.graph.state import initial_agent_state, update_game_state
    from src.state.gold_state_reader import (
        ADDR_FACING,
        ADDR_MAP_GROUP,
        ADDR_MAP_NUMBER,
        ADDR_X_COORD,
        ADDR_Y_COORD,
        MAP_ELMS_LAB,
        MAPGROUP_NEW_BARK,
    )
    from tests.fake_emulator import StarterQuestEmulator

    mem = dict(post_house_ram)
    mem[ADDR_MAP_GROUP] = MAPGROUP_NEW_BARK
    mem[ADDR_MAP_NUMBER] = MAP_ELMS_LAB
    mem[ADDR_X_COORD] = 5
    mem[ADDR_Y_COORD] = 3
    mem[ADDR_FACING] = 0

    emu = StarterQuestEmulator(mem)
    emu._elm_intro_done = True
    gs = emu.get_game_state()
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["lab_desk_dialog_done"] = True

    for _ in range(12):
        state = supervisor_node(state)
        node = state.get("next_node")
        if node == "navigator":
            state = navigator_node(state)
        elif node == "interactor":
            state = interactor_node(state)
        else:
            break
        state = apply_action_node(state, emu)
        gs = emu.get_game_state()
        state = update_game_state(state, gs)
        state = critic_node(state)
        state = memory_node(state)
        if gs.party_count >= 1:
            break

    assert gs.party_count >= 1


def test_lab_ball_row_prefers_interact_candidate():
    from src.graph.generic_interact import generic_prefer_interact_candidate

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = {
        "lab_desk_dialog_done": True,
        "active_subgoal": "Pick a Poke Ball",
        "last_action": "interact_a",
        "stuck_count": 0,
    }
    assert generic_prefer_interact_candidate(gs, state) is True


def test_navigator_at_lab_5_3_faces_ball_or_interacts():
    from src.memory.landmarks import discover_elms_lab_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 0},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["lab_desk_dialog_done"] = True
    state["known_landmarks"] = discover_elms_lab_landmarks(gs)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_right"
    assert result["last_action_result"]["target"] == (5, 3)


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
    state["lab_desk_dialog_done"] = True
    state["lab_stall_position"] = gs.position_key
    state["lab_steps_without_party"] = 12
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
    state["lab_desk_dialog_done"] = True
    state["lab_stall_position"] = gs.position_key
    state["lab_steps_without_party"] = 8
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
    state["lab_desk_dialog_done"] = True
    state["known_landmarks"] = []
    target = _navigation_target(gs, map_key=gs.map_key, state=state)
    assert target != (gs.player.x, gs.player.y)


def test_navigator_from_elm_desk_routes_down_toward_ball_after_intro():
    from src.memory.landmarks import discover_elms_lab_landmarks

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2, "facing": 12},
        raw_metadata={"has_starter": False},
        party_count=0,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["lab_desk_dialog_done"] = True
    state["known_landmarks"] = discover_elms_lab_landmarks(gs)
    starter_quest.sync_subgoals(gs, state)
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["last_action_result"]["target"] is not None
    assert "Poke Ball" in state["active_subgoal"]


def test_critic_does_not_replan_during_desk_intro_oscillation():
    gs = GameState(player={"map_group": 24, "map_id": 5, "x": 4, "y": 2})
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["lab_desk_dialog_done"] = False
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
    state["lab_desk_dialog_done"] = True
    starter_quest.sync_subgoals(gs, state)
    result = navigator_node(state)
    assert result["last_action_result"]["target"] == starter_quest.ELMS_LAB_EXIT
    assert state["active_subgoal"]


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
    state["lab_desk_dialog_done"] = True
    state["interact_action_index"] = 7
    state["last_action"] = "interact_a"
    result = interactor_node(state)
    assert result["last_action"] == "interact_a"