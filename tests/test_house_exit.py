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


def test_needs_script_wait_when_dialog_blocks_input():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={
            "mom_scene_complete": False,
            "script_mode": SCRIPT_READ,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
            "joypad_disable": 16,
        },
    )
    assert needs_script_wait(gs, {"bootstrap_complete": True}) is True


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


def test_navigation_target_1f_after_mom_is_front_door():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={"mom_scene_complete": True},
    )
    assert _navigation_target(gs, map_key="24:6") == PLAYERS_HOUSE_1F_DOOR


def test_navigator_exits_through_door_tile():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 7},
        raw_metadata={"mom_scene_complete": True},
    )
    state = initial_agent_state(gs)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_down"


def test_door_exit_helper_only_after_mom():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 6, "y": 7},
        raw_metadata={"mom_scene_complete": False},
    )
    assert _players_house_door_exit(gs) is None