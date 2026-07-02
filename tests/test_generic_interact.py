"""Tests for generic interaction policy (roadmap Phase 2)."""

from __future__ import annotations

from src.graph.generic_interact import (
    dialog_or_script_active,
    generic_is_interact_needed,
    generic_stuck_interact_fallback,
    is_rom_interact_signal,
    navigate_stuck_at_tile,
)
from src.graph.nodes import needs_interaction, supervisor_node
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.models import GameState


def _gs(**kwargs) -> GameState:
    defaults = {
        "player": {"map_group": 24, "map_id": 5, "x": 4, "y": 3},
        "raw_metadata": {},
    }
    defaults.update(kwargs)
    return GameState(**defaults)


def test_dialog_or_script_active():
    gs = _gs(in_text_box=True)
    assert dialog_or_script_active(gs) is True
    gs2 = _gs(raw_metadata={"in_script": True})
    assert dialog_or_script_active(gs2) is True


def test_navigate_stuck_triggers_interact():
    gs = _gs()
    state = {"stuck_count": 2, "last_action": "navigate_right"}
    assert navigate_stuck_at_tile(gs, state) is True


def test_outdoor_nav_stuck_does_not_trigger_generic_interact():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 9, "y": 12},
        in_text_box=False,
        raw_metadata={"joypad_disable": 0, "in_script": False},
    )
    state = {"stuck_count": 5, "last_action": "navigate_right"}
    assert is_rom_interact_signal(gs) is False
    assert generic_stuck_interact_fallback(gs, state) is False
    assert generic_is_interact_needed(gs, state) is False
    assert needs_interaction(gs, state) is False


def test_indoor_dialog_still_triggers_interact():
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={"joypad_disable": 0, "in_script": True, "mom_scene_complete": False},
    )
    state = {"stuck_count": 0, "last_action": ""}
    assert generic_stuck_interact_fallback(gs, state) or needs_interaction(gs, state)


def test_generic_is_interact_needed_text_box():
    gs = _gs(in_text_box=True, raw_metadata={"in_script": True, "has_starter": False})
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert generic_is_interact_needed(gs, state) is True
    assert needs_interaction(gs, state) is True


def test_supervisor_routes_interactor_on_dialog():
    gs = _gs(in_text_box=True, raw_metadata={"in_script": True, "has_starter": False})
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["bootstrap_complete"] = True
    result = supervisor_node(state)
    assert result["next_node"] == "interactor"
    assert result["phase"] == "interact"


def test_starter_quest_has_no_lab_phase_enum():
    import inspect

    source = inspect.getsource(starter_quest)
    assert "LabPhase" not in source
    assert "resolve_lab_pre_starter" not in source


def test_navigation_target_returns_none():
    gs = _gs(raw_metadata={"has_starter": False})
    assert starter_quest.navigation_target(gs) is None