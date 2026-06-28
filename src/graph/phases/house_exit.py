"""House-exit phase: routing, navigation, logging, and terminal success."""

from __future__ import annotations

import os
from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    PLAYERS_HOUSE_1F_DOOR,
)
from src.state.models import GameState
from src.state.script_constants import MOM_SCENE_ENTRY_POS

HOUSE_EXIT_MILESTONE = "Left house — New Bark Town"
HOUSE_EXIT_DONE_ACTION = "house_exit_done"
STAIRS_2F = (7, 0)

INDOOR_INTERACT_STUCK = int(os.getenv("INDOOR_INTERACT_STUCK", "2"))
POST_WARP_WAIT_TICKS = int(os.getenv("POST_WARP_WAIT_TICKS", "90"))
SCRIPT_WAIT_TICKS = int(os.getenv("SCRIPT_WAIT_TICKS", "45"))


def is_satisfied(gs: GameState, state: dict[str, Any]) -> bool:
    """House-exit goal complete: player on New Bark exterior after leaving the house."""
    return bool(state.get("house_exit_complete") and gs.map_key == MAP_KEY_NEW_BARK_TOWN)


def in_house_exit(gs: GameState, state: dict[str, Any] | None = None) -> bool:
    """Player is still inside the starting house (2F or 1F)."""
    state = state or {}
    if state.get("house_exit_complete"):
        return False
    return gs.map_key in (MAP_KEY_PLAYERS_HOUSE_2F, MAP_KEY_PLAYERS_HOUSE_1F)


def mom_scene_pending(gs: GameState) -> bool:
    meta = gs.raw_metadata or {}
    return gs.map_key == MAP_KEY_PLAYERS_HOUSE_1F and not meta.get("mom_scene_complete")


def needs_house_interaction(gs: GameState, state: dict[str, Any]) -> bool:
    """Extra interact signals while on 1F (beyond generic dialog detection)."""
    if gs.map_key != MAP_KEY_PLAYERS_HOUSE_1F:
        return False
    if mom_scene_pending(gs):
        return True
    if state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK:
        last = state.get("last_action", "")
        return last.startswith("navigate_") and not last.endswith("_a")
    return False


def force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    """Supervisor must route to interactor (Mom scene not finished)."""
    return mom_scene_pending(gs)


def planner_allows_llm(gs: GameState, state: dict[str, Any]) -> bool:
    """Disable LLM planner during house maps only."""
    return not in_house_exit(gs, state)


def decompose_subgoals(gs: GameState) -> list[str] | None:
    """House-phase subgoals, or None when not in this phase."""
    if gs.map_key == MAP_KEY_PLAYERS_HOUSE_2F:
        return ["Leave bedroom via stairs", "Talk to Mom downstairs", "Go to Professor Elm"]
    if gs.map_key == MAP_KEY_PLAYERS_HOUSE_1F:
        return ["Talk to Mom in the kitchen", "Leave house through front door"]
    return None


def navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[int, int] | None:
    """Navigation target for house maps; None defers to default explorer logic."""
    map_key = map_key or gs.map_key
    if map_key == MAP_KEY_PLAYERS_HOUSE_2F:
        return STAIRS_2F
    if map_key == MAP_KEY_PLAYERS_HOUSE_1F:
        if mom_scene_pending(gs):
            return (gs.player.x, gs.player.y)
        return PLAYERS_HOUSE_1F_DOOR
    return None


def door_exit_direction(gs: GameState) -> str | None:
    if not mom_scene_pending(gs) and gs.map_key == MAP_KEY_PLAYERS_HOUSE_1F:
        if (gs.player.x, gs.player.y) in (PLAYERS_HOUSE_1F_DOOR, (7, 7)):
            return "down"
    return None


def blocked_stairs_up(gs: GameState) -> bool:
    if gs.map_key != MAP_KEY_PLAYERS_HOUSE_1F:
        return False
    if not mom_scene_pending(gs):
        return False
    return gs.player.x >= 9 and gs.player.y <= 1


def prefer_interact_candidate(gs: GameState) -> bool:
    if gs.in_text_box or mom_scene_pending(gs):
        return True
    return False


def stuck_interact_fallback(gs: GameState, state: dict[str, Any]) -> bool:
    return (
        gs.map_key == MAP_KEY_PLAYERS_HOUSE_1F
        and state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    )


def on_map_change(
    map_before: str,
    gs_after: GameState,
    state: dict[str, Any],
    *,
    action: str,
) -> None:
    """House-specific side effects after a map transition."""
    if (
        action.startswith("navigate_")
        and map_before == MAP_KEY_PLAYERS_HOUSE_2F
        and gs_after.map_key == MAP_KEY_PLAYERS_HOUSE_1F
        and gs_after.player.x == MOM_SCENE_ENTRY_POS[0]
        and gs_after.player.y == MOM_SCENE_ENTRY_POS[1]
    ):
        state["post_warp_wait_steps"] = max(
            state.get("post_warp_wait_steps", 0),
            POST_WARP_WAIT_TICKS // SCRIPT_WAIT_TICKS,
        )


def on_house_exit_complete(state: dict[str, Any], gs: GameState) -> None:
    """Mark house-exit goal satisfied; supervisor routes to idle thereafter."""
    del gs  # milestone already validated map via house_milestone
    state["house_exit_complete"] = True


def house_milestone(gs: GameState, maps_visited: list[str]) -> str | None:
    if gs.map_key == MAP_KEY_PLAYERS_HOUSE_1F and maps_visited.count(MAP_KEY_PLAYERS_HOUSE_1F) == 1:
        return "Reached Player's House 1F"
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN and maps_visited.count(MAP_KEY_NEW_BARK_TOWN) == 1:
        came_from_house = MAP_KEY_PLAYERS_HOUSE_1F in maps_visited or MAP_KEY_PLAYERS_HOUSE_2F in maps_visited
        if came_from_house:
            return HOUSE_EXIT_MILESTONE
    return None


def format_map_context(gs: GameState) -> str:
    """Canonical map_key + name + coords for logs and intent cards."""
    return f"{gs.map_key} {gs.player.map_name} ({gs.player.x},{gs.player.y})"