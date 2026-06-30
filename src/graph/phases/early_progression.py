"""Post-starter progression: Route 29/30 toward Cherrygrove City."""

from __future__ import annotations

from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
)
from src.state.models import GameState

EARLY_PROGRESSION_DONE_ACTION = "early_progression_done"
MILESTONE_REACHED_CHERRYGROVE = "Reached Cherrygrove City"

EARLY_PROGRESSION_MAPS = frozenset(
    {
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
        MAP_KEY_CHERRYGROVE_CITY,
    }
)


def in_early_progression(gs: GameState, state: dict[str, Any]) -> bool:
    """Active after starter quest until Cherrygrove terminal condition."""
    if not state.get("starter_quest_complete"):
        return False
    if state.get("early_progression_complete"):
        return False
    return not is_satisfied(gs, state)


def is_satisfied(gs: GameState, state: dict[str, Any]) -> bool:
    """Terminal when Cherrygrove reached or explicit completion flag set."""
    if state.get("early_progression_complete"):
        return True
    return (
        bool(state.get("starter_quest_complete"))
        and gs.map_key == MAP_KEY_CHERRYGROVE_CITY
    )


def on_early_progression_complete(state: dict[str, Any], gs: GameState) -> None:
    del gs
    state["early_progression_complete"] = True


def planner_allows_llm(gs: GameState, state: dict[str, Any]) -> bool:
    del gs, state
    return True


def force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    del gs, state
    return False


def decompose_subgoals(gs: GameState) -> list[str] | None:
    """Post-rival subgoals by map; None when not in this phase's maps."""
    if gs.map_key not in EARLY_PROGRESSION_MAPS:
        return None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        return ["Exit New Bark east", "Cross Route 29", "Reach Cherrygrove City"]
    if gs.map_key == MAP_KEY_ROUTE_29:
        return ["Travel north on Route 29", "Reach Cherrygrove City"]
    if gs.map_key == MAP_KEY_ROUTE_30:
        return ["Travel north toward Cherrygrove", "Enter Cherrygrove City"]
    if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
        return ["Explore Cherrygrove City", "Continue toward Violet City"]
    return ["Head toward Cherrygrove City"]


def navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[int, int] | None:
    """Landmark-first targets via quest geography; grid frontier as fallback."""
    from src.graph.exploration import exploration_target
    from src.graph.quest_geography import resolve_retired_geography

    state = state or {}
    map_key = map_key or gs.map_key
    if map_key not in EARLY_PROGRESSION_MAPS:
        return None
    resolved = resolve_retired_geography(gs, state)
    if resolved is not None:
        return resolved
    return exploration_target(gs, state, skip_retired=True)


def sync_subgoals(gs: GameState, state: dict[str, Any]) -> None:
    """Refresh early-progression subgoals when this phase is active."""
    if not in_early_progression(gs, state):
        return
    subgoals = decompose_subgoals(gs)
    if not subgoals:
        return
    state["subgoals"] = subgoals
    idx = min(state.get("replan_count", 0), len(subgoals) - 1)
    state["active_subgoal"] = subgoals[idx]