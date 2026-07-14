"""Post-starter progression: Route 29/30/31 → Cherrygrove → Violet → first gym."""

from __future__ import annotations

from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
    MAP_KEY_ROUTE_31,
    MAP_KEY_ROUTE_31_VIOLET_GATE,
    MAP_KEY_VIOLET_CITY,
    MAP_KEY_VIOLET_GYM,
)
from src.state.models import GameState

EARLY_PROGRESSION_DONE_ACTION = "early_progression_done"
MILESTONE_REACHED_CHERRYGROVE = "Reached Cherrygrove City"
MILESTONE_REACHED_ROUTE_31 = "Reached Route 31"
MILESTONE_REACHED_VIOLET = "Reached Violet City"
MILESTONE_ENTERED_FIRST_GYM = "Entered Violet Gym"

EARLY_PROGRESSION_MAPS = frozenset(
    {
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
        MAP_KEY_ROUTE_31,
        MAP_KEY_CHERRYGROVE_CITY,
        MAP_KEY_ROUTE_31_VIOLET_GATE,
        MAP_KEY_VIOLET_CITY,
        MAP_KEY_VIOLET_GYM,
    }
)


def in_early_progression(gs: GameState, state: dict[str, Any]) -> bool:
    """Active after starter quest until first-gym terminal condition."""
    if not state.get("starter_quest_complete"):
        return False
    if state.get("early_progression_complete"):
        return False
    return not is_satisfied(gs, state)


def is_satisfied(gs: GameState, state: dict[str, Any]) -> bool:
    """Terminal only at first gym (Violet Gym) or explicit completion flag.

    Cherrygrove / Route 30–31 / Violet overworld are corridor milestones — not holds.
    """
    if state.get("early_progression_complete"):
        return True
    return bool(state.get("starter_quest_complete")) and gs.map_key == MAP_KEY_VIOLET_GYM


def on_early_progression_complete(state: dict[str, Any], gs: GameState) -> None:
    """Mark early progression done and set a post-arrival gym subgoal."""
    state["early_progression_complete"] = True
    # Keep a clear in-gym objective (sync_subgoals is gated off once complete).
    if gs.map_key == MAP_KEY_VIOLET_GYM:
        subgoals = ["Challenge Falkner (first gym reached)"]
        state["subgoals"] = subgoals
        state["active_subgoal"] = subgoals[0]


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
        return ["Enter Route 29", "Cross Route 29", "Reach Cherrygrove City"]
    if gs.map_key == MAP_KEY_ROUTE_29:
        return ["Travel west on Route 29", "Reach Cherrygrove City"]
    if gs.map_key == MAP_KEY_ROUTE_30:
        return [
            "Travel toward Cherrygrove or Route 31",
            "Continue toward Violet City",
        ]
    if gs.map_key == MAP_KEY_CHERRYGROVE_CITY:
        return ["Leave Cherrygrove north", "Travel Route 30/31 toward Violet City"]
    if gs.map_key == MAP_KEY_ROUTE_31:
        return ["Cross Route 31 west", "Enter Violet City"]
    if gs.map_key == MAP_KEY_ROUTE_31_VIOLET_GATE:
        return ["Pass the Violet gate", "Enter Violet City"]
    if gs.map_key == MAP_KEY_VIOLET_CITY:
        return ["Find Violet Gym entrance", "Enter Violet Gym"]
    if gs.map_key == MAP_KEY_VIOLET_GYM:
        return ["Challenge Falkner (first gym reached)"]
    return ["Head toward Violet City and the first gym"]


def navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[int, int] | None:
    """Milestone module: no coordinate routing (landmarks + exploration handle nav)."""
    del gs, map_key, state
    return None


def progression_milestone(gs: GameState, maps_visited: list[str]) -> str | None:
    """First-visit corridor milestones for early progression (Cherrygrove → gym)."""
    if (
        gs.map_key == MAP_KEY_CHERRYGROVE_CITY
        and maps_visited.count(MAP_KEY_CHERRYGROVE_CITY) == 1
    ):
        return MILESTONE_REACHED_CHERRYGROVE
    if gs.map_key == MAP_KEY_ROUTE_31 and maps_visited.count(MAP_KEY_ROUTE_31) == 1:
        return MILESTONE_REACHED_ROUTE_31
    if (
        gs.map_key == MAP_KEY_VIOLET_CITY
        and maps_visited.count(MAP_KEY_VIOLET_CITY) == 1
    ):
        return MILESTONE_REACHED_VIOLET
    if (
        gs.map_key == MAP_KEY_VIOLET_GYM
        and maps_visited.count(MAP_KEY_VIOLET_GYM) == 1
    ):
        return MILESTONE_ENTERED_FIRST_GYM
    return None


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
