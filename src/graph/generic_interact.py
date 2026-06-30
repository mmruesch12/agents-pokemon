"""Generic interaction policy (roadmap Phase 2): ROM-signal rules only."""

from __future__ import annotations

import os
from typing import Any

from src.state.gold_state_reader import MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE
from src.state.models import GameState
from src.state.script_constants import SCRIPT_READ, joypad_input_blocked

INDOOR_INTERACT_STUCK = int(os.getenv("INDOOR_INTERACT_STUCK", "2"))


def _meta(gs: GameState) -> dict[str, Any]:
    return gs.raw_metadata or {}


def dialog_or_script_active(gs: GameState) -> bool:
    """Text box open or map script still running."""
    meta = _meta(gs)
    return gs.in_text_box or bool(meta.get("in_script"))


def joypad_blocked_facing_object(gs: GameState) -> bool:
    """Movement blocked while script expects dialog input (facing NPC/object)."""
    meta = _meta(gs)
    joypad_disable = meta.get("joypad_disable", 0)
    if not joypad_input_blocked(joypad_disable):
        return False
    if meta.get("script_mode") == SCRIPT_READ:
        return True
    return dialog_or_script_active(gs)


def quest_object_interact(gs: GameState, state: dict[str, Any]) -> bool:
    """Interact at known quest object tiles when subgoals require it."""
    from src.graph.phases import starter_quest

    pos = (gs.player.x, gs.player.y)
    if (
        gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
        and not starter_quest._has_egg(gs)
        and pos == (5, 5)
    ):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_quest._has_egg(gs)
        and not starter_quest._egg_delivered(gs)
        and pos in ((4, 2), (5, 2))
    ):
        return True
    return False


def lab_interact_row(gs: GameState, state: dict[str, Any]) -> bool:
    """Pre-starter Elm lab desk/ball row — interact when subgoal expects dialog."""
    from src.graph.phases import starter_quest

    if gs.map_key != MAP_KEY_ELMS_LAB or starter_quest.has_starter(gs):
        return False
    if dialog_or_script_active(gs):
        return False
    subgoal = str(state.get("active_subgoal", "")).lower()
    pos = (gs.player.x, gs.player.y)
    if "poke ball" in subgoal or "starter" in subgoal:
        ball_tiles = {(6, 3), (7, 3), (8, 3)}
        if pos in ball_tiles or any(abs(pos[0] - bx) + abs(pos[1] - by) == 1 for bx, by in ball_tiles):
            return True
    if "elm" in subgoal and pos in ((4, 2), (5, 2), (4, 3)):
        return True
    return False


def navigate_stuck_at_tile(gs: GameState, state: dict[str, Any]) -> bool:
    """Repeated failed navigation at the same tile — try interact then replan."""
    del gs
    stuck = state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    last = state.get("last_action", "")
    return stuck and last.startswith("navigate_") and not last.endswith("_a")


def generic_is_interact_needed(gs: GameState, state: dict[str, Any]) -> bool:
    """True when ROM signals expect A/B instead of movement."""
    meta = _meta(gs)
    joypad_disable = meta.get("joypad_disable", 0)
    blocked = joypad_input_blocked(joypad_disable)
    if dialog_or_script_active(gs) and not blocked:
        return True
    if meta.get("script_mode") == SCRIPT_READ and not blocked:
        return True
    if joypad_blocked_facing_object(gs):
        return True
    if navigate_stuck_at_tile(gs, state):
        return True
    if lab_interact_row(gs, state) or quest_object_interact(gs, state):
        return True
    return False


def generic_force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    """Supervisor must route to interactor before navigator (active dialog/script)."""
    if navigate_stuck_at_tile(gs, state):
        return False
    return dialog_or_script_active(gs) or joypad_blocked_facing_object(gs)


def generic_prefer_interact_candidate(gs: GameState, state: dict[str, Any]) -> bool:
    """Navigator should offer interact when dialog is active."""
    if lab_interact_row(gs, state) or quest_object_interact(gs, state):
        return True
    return dialog_or_script_active(gs) and not navigate_stuck_at_tile(gs, state)


def generic_stuck_interact_fallback(gs: GameState, state: dict[str, Any]) -> bool:
    """Append interact candidate after navigate stuck threshold."""
    return navigate_stuck_at_tile(gs, state)