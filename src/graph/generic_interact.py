"""Generic interaction policy (roadmap Phase 2): ROM-signal rules only."""

from __future__ import annotations

import os
from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
)
from src.state.models import GameState
from src.state.script_constants import SCRIPT_READ, joypad_input_blocked

INDOOR_INTERACT_STUCK = int(os.getenv("INDOOR_INTERACT_STUCK", "2"))
INTERACT_NO_PROGRESS_RECOVERY = int(os.getenv("INTERACT_NO_PROGRESS_RECOVERY", "12"))
POCKET_STUCK_MAX_POSITIONS = 4

INDOOR_NAV_STUCK_MAPS = frozenset(
    {MAP_KEY_PLAYERS_HOUSE_1F, MAP_KEY_PLAYERS_HOUSE_2F, MAP_KEY_ELMS_LAB}
)


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


def outdoor_interact_recovery_active(gs: GameState, state: dict[str, Any]) -> bool:
    """Outdoor maps: ROM dialog is not advancing — prefer navigation recovery."""
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return False
    return state.get("interact_no_progress_count", 0) >= INTERACT_NO_PROGRESS_RECOVERY


def is_rom_interact_signal(gs: GameState) -> bool:
    """True when ROM-derived state expects dialog/button input."""
    meta = _meta(gs)
    joypad_disable = meta.get("joypad_disable", 0)
    blocked = joypad_input_blocked(joypad_disable)
    if dialog_or_script_active(gs) and not blocked:
        return True
    if meta.get("script_mode") == SCRIPT_READ and not blocked:
        return True
    if joypad_blocked_facing_object(gs):
        return True
    return False


def _parse_pocket_pos(pos: str) -> tuple[int, int] | None:
    if "," not in pos:
        return None
    parts = pos.split(",", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _pocket_positions(state: dict[str, Any]) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for item in state.get("pocket_nav_positions", []):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            positions.append((int(item[0]), int(item[1])))
        elif isinstance(item, str):
            parsed = _parse_pocket_pos(item)
            if parsed is not None:
                positions.append(parsed)
    return positions


def in_navigation_pocket(state: dict[str, Any], x: int, y: int) -> bool:
    """True when (x, y) is inside the small tile pocket from recent failed nav."""
    positions = _pocket_positions(state)
    if not positions:
        return False
    for px, py in positions:
        if (x, y) == (px, py):
            return True
        if abs(x - px) + abs(y - py) <= 1:
            return True
    return False


def record_pocket_nav_failure(state: dict[str, Any], x: int, y: int) -> None:
    """Accumulate pocket stuck when a navigate action fails to change position."""
    state["pocket_stuck_count"] = state.get("pocket_stuck_count", 0) + 1
    raw = list(state.get("pocket_nav_positions", []))
    key = f"{x},{y}"
    if key not in raw:
        raw.append(key)
    state["pocket_nav_positions"] = raw[-POCKET_STUCK_MAX_POSITIONS:]


def clear_pocket_stuck(state: dict[str, Any]) -> None:
    state["pocket_stuck_count"] = 0
    state["pocket_nav_positions"] = []


def pocket_navigate_stuck(state: dict[str, Any]) -> bool:
    """Pocket-level navigate stuck — lateral moves within pocket do not evade this."""
    stuck = state.get("pocket_stuck_count", 0) >= INDOOR_INTERACT_STUCK
    last = state.get("last_action", "")
    return stuck and last.startswith("navigate_") and not last.endswith("_a")


def navigate_stuck_at_tile(gs: GameState, state: dict[str, Any]) -> bool:
    """Repeated failed navigation at the same tile or within a small pocket."""
    del gs
    last = state.get("last_action", "")
    if not (last.startswith("navigate_") and not last.endswith("_a")):
        return False
    tile = state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    return tile or pocket_navigate_stuck(state)


def generic_is_interact_needed(gs: GameState, state: dict[str, Any]) -> bool:
    """True when ROM signals expect A/B instead of movement."""
    del state
    return is_rom_interact_signal(gs)


def generic_force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    """Supervisor must route to interactor before navigator (active dialog/script)."""
    del state
    return is_rom_interact_signal(gs)


def generic_prefer_interact_candidate(gs: GameState, state: dict[str, Any]) -> bool:
    """Navigator should offer interact when ROM signals expect dialog input."""
    del state
    return is_rom_interact_signal(gs)


def generic_stuck_interact_fallback(gs: GameState, state: dict[str, Any]) -> bool:
    """Append interact candidate after navigate stuck — indoor maps only."""
    if is_rom_interact_signal(gs):
        return True
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return navigate_stuck_at_tile(gs, state)
    return False