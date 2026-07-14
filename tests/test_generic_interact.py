"""Tests for generic interaction policy (roadmap Phase 2)."""

from __future__ import annotations

from src.graph.generic_interact import (
    dialog_or_script_active,
    generic_is_interact_needed,
    generic_stuck_interact_fallback,
    interact_stall_recovery_active,
    is_rom_interact_signal,
    navigate_stuck_at_tile,
)
from src.graph.nodes import needs_interaction, navigator_node, supervisor_node
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.models import GameState
from src.state.script_constants import SCRIPT_READ


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


def test_script_read_alone_without_active_script_is_not_interact_signal():
    """Idle SCRIPT_READ residue must not force permanent A spam."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=False,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": False,
            "in_script": False,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    assert is_rom_interact_signal(gs) is False
    assert needs_interaction(gs, {"bootstrap_complete": True, "stuck_count": 0}) is False


def test_interact_stall_recovery_breaks_sticky_indoor_dialog_flags():
    """True residue: textbox closed, sticky script flags, fruitless A → navigate."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=False,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    # Short streak is enough once the textbox is closed (residue, not live pages).
    state["interact_no_progress_count"] = 8
    state["short_term_history"] = ["interact:a@9,1"] * 5
    assert interact_stall_recovery_active(gs, state) is True
    assert needs_interaction(gs, state) is False
    assert generic_is_interact_needed(gs, state) is False
    result = supervisor_node(state)
    assert result["next_node"] == "navigator"


def test_live_textbox_short_stall_does_not_escape():
    """Open textbox + short no-progress streak must keep A (post-Mom multi-page)."""
    from src.graph.generic_interact import should_arm_interact_stall

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 8
    state["short_term_history"] = ["interact:a@9,1"] * 5
    assert should_arm_interact_stall(gs, 8) is False
    assert interact_stall_recovery_active(gs, state) is False
    assert needs_interaction(gs, state) is True
    result = supervisor_node(state)
    assert result["next_node"] == "interactor"


def test_live_textbox_long_stall_still_escapes():
    """Open textbox with long fruitless streak (true sticky residue) → navigate."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 22
    state["short_term_history"] = ["interact:a@9,1"] * 5
    assert interact_stall_recovery_active(gs, state) is True
    assert needs_interaction(gs, state) is False
    result = supervisor_node(state)
    assert result["next_node"] == "navigator"


def test_post_mom_short_interact_streak_does_not_escape():
    """Brief post-Mom A presses must not nav-escape (live follow-up dialog)."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 0
    # Shorter than INTERACT_STALL_STREAK (8) — still finish dialog with A.
    state["short_term_history"] = ["interact:a@9,1"] * 5
    assert interact_stall_recovery_active(gs, state) is False
    assert needs_interaction(gs, state) is True


def test_mom_history_alone_does_not_arm_recovery_after_flag():
    """MeetMom A spam in history must not arm escape the instant the flag sets."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 0
    state["short_term_history"] = ["interact:a@9,1"] * 17
    assert interact_stall_recovery_active(gs, state) is False
    assert needs_interaction(gs, state) is True


def test_joypad_blocked_suppresses_interact_stall_recovery():
    """Hard joypad disable means navigation cannot succeed — keep interacting."""
    from src.state.script_constants import JOYPAD_DISABLE_INPUT_MASK

    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": JOYPAD_DISABLE_INPUT_MASK,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 20
    state["short_term_history"] = ["interact:a@9,1"] * 8
    state["interact_stall_escape"] = True
    assert interact_stall_recovery_active(gs, state) is False
    assert needs_interaction(gs, state) is True


def test_navigator_prefers_path_not_a_after_interact_stall():
    """After interact stall recovery, navigator must not force navigate_a."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=False,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 8
    state["short_term_history"] = ["interact:a@9,1"] * 6
    state["stuck_count"] = 3
    result = navigator_node(state)
    assert result["last_action"].startswith("navigate_")
    assert result["last_action"] != "navigate_a"
    assert "a" not in result["last_action_result"]["candidates"][:1]


def test_interact_stall_escape_latches_through_mixed_history():
    """One navigate attempt must not re-arm force-interact A spam."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=False,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 8
    state["short_term_history"] = ["interact:a@9,1"] * 5
    assert interact_stall_recovery_active(gs, state) is True
    assert state.get("interact_stall_escape") is True
    # Mixed history would break pure interact-streak detection without latch.
    state["short_term_history"] = ["interact:a@9,1"] * 4 + ["navigate:down@9,1"]
    assert interact_stall_recovery_active(gs, state) is True
    assert needs_interaction(gs, state) is False


def test_live_textbox_clears_false_stall_latch():
    """Mid-dialog nav latch under long threshold is dropped so A continues."""
    gs = GameState(
        player={"map_group": 24, "map_id": 6, "x": 9, "y": 1},
        in_text_box=True,
        raw_metadata={
            "script_mode": SCRIPT_READ,
            "script_active": True,
            "in_script": True,
            "joypad_disable": 0,
            "mom_scene_complete": True,
        },
    )
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["interact_no_progress_count"] = 5
    state["interact_stall_escape"] = True
    state["short_term_history"] = ["interact:a@9,1"] * 5
    assert interact_stall_recovery_active(gs, state) is False
    assert state.get("interact_stall_escape") is not True
    assert needs_interaction(gs, state) is True
