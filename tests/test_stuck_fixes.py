"""Regression tests for WRAM alignment, stuck detection, and indoor navigation."""

from __future__ import annotations

from src.emulator.bootstrap import MAP_GROUP_ADDR, MAP_NUMBER_ADDR
from src.graph.nodes import (
    _navigation_target,
    _update_stuck_from_movement,
    navigator_node,
)
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