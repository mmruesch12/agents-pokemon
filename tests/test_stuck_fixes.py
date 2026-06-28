"""Regression tests for WRAM alignment, stuck detection, and indoor navigation."""

from __future__ import annotations

from src.emulator.bootstrap import MAP_GROUP_ADDR, MAP_NUMBER_ADDR
from src.graph.nodes import (
    _effective_map_key,
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
    ByteArrayReader,
    GoldStateReader,
)
from src.state.models import GameState


def test_reader_uses_same_map_addresses_as_bootstrap():
    assert ADDR_MAP_GROUP == MAP_GROUP_ADDR
    assert ADDR_MAP_NUMBER == MAP_NUMBER_ADDR


def test_reader_reads_indoor_map_from_bootstrap_addresses():
    mem = {
        ADDR_MAP_GROUP: 3,
        ADDR_MAP_NUMBER: 4,
        ADDR_X_COORD: 3,
        ADDR_Y_COORD: 5,
    }
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    assert gs.map_key == "3:4"
    assert gs.player.x == 3
    assert gs.player.y == 5
    assert gs.player.map_name == "Player's House 2F"


def test_probe_oscillation_does_not_count_as_movement():
    state = {"stuck_count": 5}
    _update_stuck_from_movement(
        state,
        "navigate_right",
        "3:4:3:5",
        "3:4:3:5",
        probe_before=55,
        probe_after=64,
    )
    assert state["stuck_count"] == 6


def test_navigation_target_players_house_goes_south():
    gs = GameState(player={"map_group": 3, "map_id": 4, "x": 3, "y": 5})
    target = _navigation_target(gs, map_key="3:4")
    assert target == (3, 7)


def test_effective_map_key_falls_back_to_loaded_map():
    gs = GameState(player={"map_group": 0, "map_id": 0, "x": 3, "y": 5})
    state = initial_agent_state(gs)
    state["loaded_map_key"] = [3, 4]
    assert _effective_map_key(gs, state) == "3:4"


def test_navigator_players_house_moves_down_not_right():
    gs = GameState(player={"map_group": 3, "map_id": 4, "x": 3, "y": 2})
    state = initial_agent_state(gs)
    result = navigator_node(state)
    assert result["last_action"] == "navigate_down"
    assert "down" in result["last_action_result"]["candidates"]