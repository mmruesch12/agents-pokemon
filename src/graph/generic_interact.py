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
INTERACT_NO_PROGRESS_RECOVERY = int(
    os.getenv("INTERACT_NO_PROGRESS_RECOVERY", "22")
)
# Outdoor multi-page NPC dialog can need many A presses; keep this below the
# thrash budget so gate/sign residue cannot soft-lock forever (live R29 gate).
OUTDOOR_OPEN_TEXTBOX_RECOVERY = int(
    os.getenv("OUTDOOR_OPEN_TEXTBOX_RECOVERY", "18")
)
# When script_pos freezes under outdoor A, abort far sooner — further A can
# hard-lock the overworld (live Route 30 (13,24) script_pos stuck forever).
OUTDOOR_FROZEN_SCRIPT_RECOVERY = int(
    os.getenv("OUTDOOR_FROZEN_SCRIPT_RECOVERY", "5")
)
# Faster escape for same-tile A-spam when script flags stay sticky (e.g. post-Mom).
INTERACT_STALL_STREAK = int(os.getenv("INTERACT_STALL_STREAK", "8"))
INTERACT_STALL_MIN_HISTORY = int(os.getenv("INTERACT_STALL_MIN_HISTORY", "5"))
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


def _same_tile_interact_streak(history: list[str], *, min_count: int) -> bool:
    """True when the last min_count history entries are interact at one tile."""
    if len(history) < min_count:
        return False
    positions: set[str] = set()
    for item in history[-min_count:]:
        if "@" not in item:
            return False
        action, pos = item.split("@", 1)
        if action.split(":")[0] != "interact":
            return False
        positions.add(pos)
    return len(positions) == 1


def arm_interact_stall_escape(state: dict[str, Any]) -> None:
    """Latch navigation preference until clear_interact_stall_escape."""
    state["interact_stall_escape"] = True


def clear_interact_stall_escape(state: dict[str, Any]) -> None:
    state["interact_stall_escape"] = False


def should_arm_interact_stall(gs: GameState, count: int) -> bool:
    """True when a fruitless interact streak is long enough to prefer navigation.

    Open textbox (indoor *or* outdoor): never arm nav-escape. Movement cannot
    dismiss story/NPC dialog, and outdoor B/nav while SCRIPT_READ is open
    soft-locks the overworld (live Route 30 (14,23) after B recovery).

    Closed-textbox residue uses the short INTERACT_STALL_STREAK.
    """
    if gs.in_text_box:
        return False
    return count >= INTERACT_STALL_STREAK


def outdoor_script_frozen(gs: GameState, state: dict[str, Any]) -> bool:
    """True when outdoor script residue is frozen *without* an open textbox.

    While ``in_text_box`` is true, keep A — arming nav-escape lets recovery
    press B, which hard-locks SCRIPT_READ dialogs (live R30 stuck_122).
    """
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return False
    if gs.in_text_box:
        return False
    meta = _meta(gs)
    if not (meta.get("in_script") or meta.get("script_active")):
        return False
    frozen = int(state.get("outdoor_script_frozen_count", 0))
    return frozen >= OUTDOOR_FROZEN_SCRIPT_RECOVERY


def interact_stall_recovery_active(gs: GameState, state: dict[str, Any]) -> bool:
    """Prefer navigation after unproductive interact spam (indoor or outdoor).

    Covers sticky SCRIPT_READ / in_script residue after a scene ends: A no longer
    advances meaningful dialog, but ROM flags still look like dialog is active.

    Once armed (interact_stall_escape), recovery stays latched through mixed
    navigate/interact history until position or script progress clears it —
    otherwise a single navigate attempt breaks the interact streak and forces A again.

    Guards:
    - MeetMom pending: movement is locked; never nav-escape mid-scene.
    - Joypad hard-disabled: movement cannot succeed; keep A/B.
    - Live open textbox: never nav-escape (long multi-page freezes still need A).
    - Require interact_no_progress_count + same-tile streak (not history alone) so
      post-Mom live dialog after EVENT_PLAYERS_HOUSE_MOM_1 still finishes with A.
    """
    meta = _meta(gs)
    # Never escape while MeetMom is still pending — movement is locked at entry.
    if gs.map_key == MAP_KEY_PLAYERS_HOUSE_1F and not meta.get("mom_scene_complete"):
        if state.get("interact_stall_escape"):
            clear_interact_stall_escape(state)
        return False
    joypad_disable = meta.get("joypad_disable", 0)
    if joypad_input_blocked(joypad_disable):
        # Cannot leave the tile while pret skips joypad — keep interacting.
        if state.get("interact_stall_escape"):
            clear_interact_stall_escape(state)
        return False
    count = int(state.get("interact_no_progress_count", 0))
    # Any open textbox clears nav latch — keep A until dialog closes.
    # Outdoor B/nav mid-SCRIPT_READ soft-locks (live Route 30 (14,23)).
    if state.get("interact_stall_escape") and gs.in_text_box:
        clear_interact_stall_escape(state)
    elif state.get("interact_stall_escape"):
        return True
    history = list(state.get("short_term_history", []))
    same = _same_tile_interact_streak(
        history, min_count=INTERACT_STALL_MIN_HISTORY
    )
    # Require no-progress count — history alone is wrong because MeetMom fills
    # short_term_history with interacts, then the event flag flips while the
    # player is still movement-locked for remaining dialog.
    if should_arm_interact_stall(gs, count) and same:
        arm_interact_stall_escape(state)
        return True
    if count >= INTERACT_NO_PROGRESS_RECOVERY and not is_rom_interact_signal(gs):
        arm_interact_stall_escape(state)
        return True
    return False


def outdoor_interact_recovery_active(gs: GameState, state: dict[str, Any]) -> bool:
    """Outdoor maps: prefer navigation after unproductive interact spam.

    Never nav-escape while ``in_text_box`` is open — pure A eventually clears
    multi-page NPC/sign dialog (observed 2–36 A presses). Escaping to navigator
    injects B, which hard-locks SCRIPT_READ (live Route 30 stuck_122).

    Closed-textbox script residue and high stuck still arm recovery.
    """
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return False
    if gs.in_text_box:
        return False
    if interact_stall_recovery_active(gs, state):
        return True
    stuck = int(state.get("stuck_count", 0))
    no_progress = int(state.get("interact_no_progress_count", 0))
    # Soft outdoor thrash: same tile A-spam with mild stuck (live Route 29 gate).
    if stuck >= 2 and no_progress >= INTERACT_STALL_STREAK:
        arm_interact_stall_escape(state)
        return True
    if outdoor_script_frozen(gs, state):
        arm_interact_stall_escape(state)
        return True
    if stuck >= 5 and no_progress >= 2:
        arm_interact_stall_escape(state)
        return True
    if is_rom_interact_signal(gs):
        return False
    return no_progress >= INTERACT_NO_PROGRESS_RECOVERY


def is_rom_interact_signal(gs: GameState) -> bool:
    """True when ROM-derived state expects dialog/button input."""
    meta = _meta(gs)
    joypad_disable = meta.get("joypad_disable", 0)
    blocked = joypad_input_blocked(joypad_disable)
    outdoor = gs.map_key not in INDOOR_NAV_STUCK_MAPS
    # Outdoor: only open textbox is a real dialog signal. Sticky SCRIPT_READ /
    # in_script / joypad-disable *without* a textbox is residue — forcing A
    # soft-locks the overworld (live R30 (1,11)/(3,18); R31 (28,15) after R30
    # entry; gym22/47). Walk path0 instead; real NPC/sign pages set in_text_box.
    # Joypad-disable during an open textbox still needs A (trainer/rival cutscene).
    if outdoor:
        return bool(gs.in_text_box)
    if dialog_or_script_active(gs) and not blocked:
        return True
    # SCRIPT_READ alone is idle residue; require an active script bit.
    script_live = bool(meta.get("script_active") or meta.get("in_script"))
    if meta.get("script_mode") == SCRIPT_READ and script_live and not blocked:
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


def _lab_ball_pick_nav_preferred(gs: GameState, state: dict[str, Any]) -> bool:
    """True when Elm desk intro is done and we should walk to the balls, not A-spam.

    Sticky SCRIPT_READ residue at the desk (no open textbox) kept the bedroom
    burn soft-lock reloading while never choosing a starter.
    """
    if gs.map_key != MAP_KEY_ELMS_LAB or gs.in_text_box:
        return False
    subgoal = (state.get("active_subgoal") or "").lower()
    return "poke ball" in subgoal or "potion" in subgoal


def generic_is_interact_needed(gs: GameState, state: dict[str, Any]) -> bool:
    """True when ROM signals expect A/B instead of movement."""
    if interact_stall_recovery_active(gs, state):
        return False
    # Soft-lock tiles session-blocked after hard reload: do not re-pin interactor
    # for sticky residue (live R30 (12,14) A-spam). Still A if a textbox is open.
    if _standing_on_session_blocked_tile(gs, state) and not gs.in_text_box:
        return False
    if _lab_ball_pick_nav_preferred(gs, state):
        return False
    return is_rom_interact_signal(gs)


def generic_force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    """Supervisor must route to interactor before navigator (active dialog/script)."""
    if interact_stall_recovery_active(gs, state):
        return False
    if _standing_on_session_blocked_tile(gs, state) and not gs.in_text_box:
        return False
    if _lab_ball_pick_nav_preferred(gs, state):
        return False
    return is_rom_interact_signal(gs)


def _standing_on_session_blocked_tile(gs: GameState, state: dict[str, Any]) -> bool:
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return False
    from src.graph.pathfinding import session_blocked_for_map

    blocked = session_blocked_for_map(state, gs.map_key)
    return (gs.player.x, gs.player.y) in blocked


def generic_prefer_interact_candidate(gs: GameState, state: dict[str, Any]) -> bool:
    """Navigator should offer interact when ROM signals expect dialog input."""
    if interact_stall_recovery_active(gs, state):
        return False
    if _standing_on_session_blocked_tile(gs, state) and not gs.in_text_box:
        return False
    return is_rom_interact_signal(gs)


def generic_stuck_interact_fallback(gs: GameState, state: dict[str, Any]) -> bool:
    """Append interact candidate after navigate stuck — indoor maps only."""
    if interact_stall_recovery_active(gs, state):
        return False
    if is_rom_interact_signal(gs) and not _standing_on_session_blocked_tile(gs, state):
        return True
    if gs.map_key in INDOOR_NAV_STUCK_MAPS:
        return navigate_stuck_at_tile(gs, state)
    return False
