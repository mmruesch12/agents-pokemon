"""Tests for script-wait routing heuristics."""

from __future__ import annotations

from src.graph.nodes import needs_script_wait
from src.graph.state import initial_agent_state
from src.state.models import GameState
from src.state.script_constants import (
    SCRIPT_FLAG_SCRIPT_RUNNING,
    SCRIPT_READ,
    SCRIPT_WAIT_MOVEMENT,
)


def test_no_wait_on_2f_garbage_script_bytes():
    gs = GameState(
        player={"map_group": 24, "map_id": 7, "x": 3, "y": 4},
        raw_metadata={
            "script_mode": 255,
            "script_running": 240,
            "joypad_disable": 1,
            "mom_scene_complete": False,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    assert needs_script_wait(gs, state) is False


def test_no_wait_during_mom_dialog_when_input_allowed():
    """joypad_disable=3 does not block input (pret bits 4/6/7 only)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_running": 12,
            "joypad_disable": 3,
            "mom_scene_complete": False,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    assert needs_script_wait(gs, state) is False


def test_wait_during_mom_cutscene_when_input_blocked():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
            "joypad_disable": 16,  # bit 4 — pret blocks joypad reads
            "mom_scene_complete": False,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    assert needs_script_wait(gs, state) is True


def test_wait_during_scripted_movement():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 0},
        raw_metadata={
            "script_mode": SCRIPT_WAIT_MOVEMENT,
            "script_flags": SCRIPT_FLAG_SCRIPT_RUNNING,
            "joypad_disable": 0,
            "mom_scene_complete": False,
        },
    )
    assert needs_script_wait(gs, {"bootstrap_complete": True}) is True