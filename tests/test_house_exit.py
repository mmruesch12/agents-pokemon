"""Tests for Player's House 1F Mom dialog and front-door exit."""

from __future__ import annotations

from src.graph.nodes import (
    _navigation_target,
    _players_house_door_exit,
    interactor_node,
    needs_interaction,
    needs_script_wait,
    navigator_node,
    supervisor_node,
    waiter_node,
)
from src.state.script_constants import SCRIPT_FLAG_SCRIPT_RUNNING, SCRIPT_READ
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    ADDR_EVENT_FLAGS,
    EVENT_PLAYERS_HOUSE_MOM_1,
    PLAYERS_HOUSE_1F_DOOR,
    has_event_flag,
)
from src.state.models import GameState


def test_has_event_flag_mom_scene():
    flag_byte = ADDR_EVENT_FLAGS + (EVENT_PLAYERS_HOUSE_MOM_1 // 8)
    flag_bit = EVENT_PLAYERS_HOUSE_MOM_1 % 8
    mem = {flag_byte: 1 << flag_bit}

    class Reader:
        def read_byte(self, address: int) -> int:
            return mem.get(address, 0)

    assert has_event_flag(Reader(), EVENT_PLAYERS_HOUSE_MOM_1) is True
    assert has_event_flag(Reader(), EVENT_PLAYERS_HOUSE_MOM_1 + 1) is False


def test_needs_interaction_on_1f_before_mom_scene():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={"mom_scene_complete": False},
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    assert needs_interaction(gs, state) is True


def test_supervisor_routes_to_interactor_during_mom_dialog_with_joypad_3():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "mom_scene_complete": False,
            "script_mode": SCRIPT_READ,
            "script_running": 12,
            "joypad_disable": 3,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    result = supervisor_node(state)
    assert result["next_node"] == "interactor"


def test_supervisor_routes_to_interactor_on_mom_dialog():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "mom_scene_complete": False,
            "script_mode": SCRIPT_READ,
            "script_running": 0,
            "joypad_disable": 0,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    result = supervisor_node(state)
    assert result["next_node"] == "interactor"


def test_script_read_with_blocked_joypad_routes_to_interact_not_wait():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={
            "mom_scene_complete": False,
            "script_mode": SCRIPT_READ,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
            "joypad_disable": 16,
            "in_script": True,
        },
        in_text_box=True,
    )
    state = {"bootstrap_complete": True}
    assert needs_script_wait(gs, state) is False
    assert needs_interaction(gs, state) is True


def test_waiter_ticks_without_input():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={
            "script_mode": 2,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
        },
    )
    state = initial_agent_state(gs)
    result = waiter_node(state)
    assert result["last_action"] == "wait_script"
    assert result["next_node"] == "critic"


def test_interactor_presses_a():
    gs = GameState(player={"map_group": 24, "map_id": 6, "x": 9, "y": 1}, in_text_box=True)
    state = initial_agent_state(gs)
    result = interactor_node(state)
    assert result["last_action"] == "interact_a"
    assert result["next_node"] == "critic"


def test_navigation_target_1f_before_mom_is_current_tile():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={"mom_scene_complete": False},
    )
    assert _navigation_target(gs, map_key="24:6") == (9, 1)


def test_navigation_target_1f_after_mom_biases_corridor_from_kitchen():
    from src.graph.phases.house_exit import PLAYERS_HOUSE_1F_CORRIDOR

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 7, "y": 2},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(gs, map_key="24:6") == PLAYERS_HOUSE_1F_CORRIDOR

    after_mom = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(after_mom, map_key="24:6") == PLAYERS_HOUSE_1F_DOOR

    at_door_row = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 6},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(at_door_row, map_key="24:6") == PLAYERS_HOUSE_1F_DOOR


def test_navigator_exits_through_door_tile():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 7},
        raw_metadata={"mom_scene_complete": True},
    )
    state = initial_agent_state(gs)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_down"


def test_navigation_target_at_corridor_advances_to_door():
    from src.graph.phases.house_exit import PLAYERS_HOUSE_1F_CORRIDOR

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 8, "y": 5},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(gs, map_key="24:6") == PLAYERS_HOUSE_1F_DOOR


def test_door_exit_direction_from_corridor():
    from src.graph.phases.house_exit import door_exit_direction

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 8, "y": 5},
        raw_metadata={"mom_scene_complete": True},
    )
    assert door_exit_direction(gs) is None


def test_corridor_select_navigation_action_uses_path_not_door_exit():
    from src.graph.nodes import (
        _navigation_candidates,
        _navigation_target,
        _players_house_door_exit,
        select_navigation_action,
    )
    from src.graph.pathfinding import find_path

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 8, "y": 5},
        raw_metadata={"mom_scene_complete": True},
    )
    state = initial_agent_state(gs)
    state["stuck_count"] = 0
    target = _navigation_target(gs, map_key="24:6", state=state)
    path = find_path(
        gs.player.x,
        gs.player.y,
        target[0],
        target[1],
        map_key="24:6",
        state=state,
    )
    candidates = _navigation_candidates(gs, target, path, state)
    door_exit = _players_house_door_exit(gs, state)
    assert door_exit is None
    action = select_navigation_action(
        door_exit=door_exit,
        path=path,
        llm_choice=None,
        candidates=candidates,
        stuck_count=0,
        gs=gs,
        state=state,
        target=target,
    )
    assert action == "left"
    assert "down" not in candidates[:1]


def test_door_exit_direction_from_door_approach_row():
    from src.graph.phases.house_exit import door_exit_direction

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 6},
        raw_metadata={"mom_scene_complete": True},
    )
    assert door_exit_direction(gs) == "down"


def test_door_exit_helper_only_after_mom():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 7},
        raw_metadata={"mom_scene_complete": False},
    )
    assert _players_house_door_exit(gs) is None