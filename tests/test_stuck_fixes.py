"""Regression tests for WRAM alignment, stuck detection, and indoor navigation."""

from __future__ import annotations

from src.emulator.bootstrap import MAP_GROUP_ADDR, MAP_NUMBER_ADDR
from src.graph.generic_interact import (
    generic_stuck_interact_fallback,
    pocket_navigate_stuck,
)
from src.graph.pathfinding import record_session_blocked
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
    history = [
        "navigate:up@1,1",
        "navigate:down@1,2",
        "navigate:left@0,1",
        "navigate:right@1,1",
        "navigate:up@2,1",
        "navigate:down@2,2",
    ] * 3
    assert _history_oscillates(history, min_cycles=2, max_positions=4) is False


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
    path = find_path(44, 8, 10, 5, map_key="24:3", state=state)
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
        target=(10, 5),
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
        target=(10, 5),
    )
    assert action != "left"


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


def test_interact_without_script_progress_blocks_tile_and_increments_stuck():
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
    state: dict = {"stuck_count": 0}
    script_key = (31532, True, 1, False)
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
    assert action == "down"


def test_select_navigation_forces_east_out_of_route_29_sign_trap():
    from src.graph.nodes import select_navigation_action

    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 14, "y": 14})
    state: dict = {"short_term_history": []}
    action = select_navigation_action(
        door_exit=None,
        path=["up", "left", "left"],
        llm_choice="up",
        candidates=["left", "right", "down", "up"],
        stuck_count=0,
        gs=gs,
        state=state,
        target=(10, 5),
    )
    assert action == "right"


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


def test_navigation_candidates_omit_blocked_primary_at_route_29_y11_trap():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 23, "y": 11})
    path = ["right", "up", "left"]
    candidates = _navigation_candidates(gs, (10, 5), path, {})
    assert "left" not in candidates
    assert "right" in candidates


def test_outdoor_interact_suppressed_on_session_blocked_standing_tile():
    from src.graph.generic_interact import generic_prefer_interact_candidate
    from src.graph.pathfinding import record_session_blocked

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 38, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state: dict = {}
    record_session_blocked(state, "24:3", 38, 14)
    assert generic_prefer_interact_candidate(gs, state) is False


def test_navigation_skips_interact_candidate_during_outdoor_recovery():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=False,
        raw_metadata={"script_pos": 1, "script_mode": 0, "in_script": False},
    )
    state = initial_agent_state(gs)
    state["interact_no_progress_count"] = 22
    candidates = _navigation_candidates(gs, (10, 5), ["up", "right"], state)
    assert "a" not in candidates


def test_outdoor_recovery_suppressed_while_rom_expects_dialog():
    from src.graph.generic_interact import outdoor_interact_recovery_active

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state = {"interact_no_progress_count": 22}
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
    from src.graph.nodes import needs_interaction, planner_node

    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 41, "y": 14},
        in_text_box=True,
        raw_metadata={"script_pos": 1, "script_mode": 1, "in_script": True},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["interact_no_progress_count"] = 22
    assert needs_interaction(gs, state) is True
    result = planner_node(state)
    assert result["next_node"] == "interactor"


def test_critic_replans_on_interact_no_progress_even_during_dialog():
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
    assert result["critic_verdict"] == "replan"
    assert result["should_replan"] is True


def test_select_navigation_prefers_path_over_llm_when_arbitrating():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 38, "y": 14})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:up@38,14"] * 3
    action = select_navigation_action(
        door_exit=None,
        path=["right", "up", "left"],
        llm_choice="up",
        candidates=["up", "right", "down"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=(10, 5),
    )
    assert action == "right"


def test_select_navigation_skips_repeat_dir_in_path_prefix():
    gs = GameState(player={"map_group": 24, "map_id": 3, "x": 38, "y": 14})
    state = initial_agent_state(gs)
    state["short_term_history"] = ["navigate:up@38,14"] * 3
    action = select_navigation_action(
        door_exit=None,
        path=["up", "right", "down"],
        llm_choice="up",
        candidates=["up", "right", "down"],
        stuck_count=5,
        gs=gs,
        state=state,
        target=(10, 5),
    )
    assert action == "right"


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
        target=(10, 5),
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