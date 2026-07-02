"""Starter-quest phase: milestone checks only (roadmap Phase 2 shrink)."""

from __future__ import annotations

from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
)
from src.state.models import BattlePhase, GameState

STARTER_QUEST_DONE_ACTION = "starter_quest_done"
MILESTONE_CHOSE_STARTER = "Chose first Pokemon"
MILESTONE_ENTERED_LAB = "Entered Elm's lab"
MILESTONE_MR_POKEMON = "Reached Mr. Pokemon's house"
MILESTONE_EGG_DELIVERED = "Delivered Mystery Egg to Elm"
MILESTONE_RIVAL_BATTLE = "First rival battle"

# ROM-gate coordinates only (not navigation sources).
ELMS_LAB_EXIT = (4, 11)
ELMS_LAB_DESK_TILES = frozenset({(4, 2), (5, 2)})
POST_WARP_WAIT_TICKS = 90
SCRIPT_WAIT_TICKS = 45

STARTER_QUEST_MAPS = frozenset(
    {
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ELMS_LAB,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
        MAP_KEY_MR_POKEMONS_HOUSE,
    }
)


def _meta(gs: GameState) -> dict[str, Any]:
    return gs.raw_metadata or {}


def starter_flag_set(gs: GameState) -> bool:
    return bool(_meta(gs).get("has_starter"))


def has_starter(gs: GameState) -> bool:
    return starter_flag_set(gs) and gs.party_count >= 1


def _has_egg(gs: GameState) -> bool:
    return bool(_meta(gs).get("has_mystery_egg"))


def _egg_delivered(gs: GameState) -> bool:
    return bool(_meta(gs).get("egg_delivered"))


def _in_rival_battle(gs: GameState) -> bool:
    return gs.battle.in_battle and gs.battle.phase == BattlePhase.TRAINER


def is_satisfied(gs: GameState, state: dict[str, Any]) -> bool:
    del gs
    return bool(state.get("starter_quest_complete"))


def in_starter_quest(gs: GameState, state: dict[str, Any] | None = None) -> bool:
    state = state or {}
    if not state.get("house_exit_complete"):
        return False
    if state.get("starter_quest_complete"):
        return False
    return gs.map_key in STARTER_QUEST_MAPS or not _egg_delivered(gs)


def lab_scene_pending(gs: GameState) -> bool:
    """Elm lab script/dialog still running (ROM-derived)."""
    if gs.map_key != MAP_KEY_ELMS_LAB:
        return False
    from src.graph.generic_interact import dialog_or_script_active

    return dialog_or_script_active(gs)


def ensure_house_exit_complete(gs: GameState, state: dict[str, Any]) -> None:
    if state.get("house_exit_complete"):
        return
    maps = state.get("maps_visited", [])
    from_house = MAP_KEY_PLAYERS_HOUSE_1F in maps or MAP_KEY_PLAYERS_HOUSE_2F in maps
    if from_house and gs.map_key in STARTER_QUEST_MAPS:
        state["house_exit_complete"] = True


def _desk_area_visited(state: dict[str, Any]) -> bool:
    """True once the player has stood on an Elm desk approach tile this session."""
    visited = set(state.get("visited_positions", []))
    desk_keys = {f"{MAP_KEY_ELMS_LAB}:{x}:{y}" for x, y in ELMS_LAB_DESK_TILES}
    return bool(desk_keys & visited)


def ensure_lab_desk_visits_for_snapshot(gs: GameState, state: dict[str, Any]) -> None:
    """Fast-start on ball row (y=3) implies Elm desk intro already happened."""
    if gs.map_key != MAP_KEY_ELMS_LAB or has_starter(gs) or gs.player.y != 3:
        return
    visited = list(state.get("visited_positions", []))
    for x, y in ELMS_LAB_DESK_TILES:
        key = f"{MAP_KEY_ELMS_LAB}:{x}:{y}"
        if key not in visited:
            visited.append(key)
    state["visited_positions"] = visited


def _subgoal_index(gs: GameState, state: dict[str, Any]) -> int:
    if not has_starter(gs):
        if gs.map_key == MAP_KEY_ELMS_LAB:
            if lab_scene_pending(gs):
                return 0
            if _desk_area_visited(state) and not lab_scene_pending(gs):
                pos = (gs.player.x, gs.player.y)
                if gs.player.y >= 3:
                    return 1
                if pos in ELMS_LAB_DESK_TILES:
                    return 1
        return 0
    if not _has_egg(gs):
        return 0
    if not _egg_delivered(gs):
        return 1
    return 2


def sync_subgoals(gs: GameState, state: dict[str, Any]) -> None:
    ensure_house_exit_complete(gs, state)
    if not state.get("house_exit_complete"):
        return
    subgoals = decompose_subgoals(gs)
    if not subgoals:
        return
    state["subgoals"] = subgoals
    idx = min(_subgoal_index(gs, state), len(subgoals) - 1)
    state["active_subgoal"] = subgoals[idx]


def planner_allows_llm(gs: GameState, state: dict[str, Any]) -> bool:
    if gs.map_key not in (MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE):
        return True
    return state.get("stuck_count", 0) >= 3


def decompose_subgoals(gs: GameState) -> list[str] | None:
    if not has_starter(gs):
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return ["Enter Elm's lab", "Listen to Elm", "Choose a starter"]
        if gs.map_key == MAP_KEY_ELMS_LAB:
            return ["Talk to Elm", "Pick a Poke Ball", "Receive Potion from aide"]
        return None
    if not _has_egg(gs):
        return ["Enter Route 29", "Cross Route 29", "Visit Mr. Pokemon's house"]
    if not _egg_delivered(gs):
        return ["Return to New Bark", "Give Mystery Egg to Elm"]
    return ["Battle rival", "Heal if needed"]


def interior_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    """Landmark id for Elm lab interior targets from active milestone subgoal."""
    from src.memory.landmarks import ELMS_LAB_BALL_APPROACH_ID, ELMS_LAB_DESK_APPROACH_ID

    if gs.map_key != MAP_KEY_ELMS_LAB or has_starter(gs):
        return None
    sync_subgoals(gs, state)
    subgoal = (state.get("active_subgoal") or "").lower()
    if "poke ball" in subgoal or "potion" in subgoal:
        return ELMS_LAB_BALL_APPROACH_ID
    return ELMS_LAB_DESK_APPROACH_ID


def navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[int, int] | None:
    """Milestone module: no coordinate routing (landmarks + exploration handle nav)."""
    del gs, map_key, state
    return None


def door_exit_direction(
    gs: GameState,
    *,
    door: tuple[int, int] | None = None,
) -> str | None:
    """Cardinal to step through a discovered warp tile (caller supplies landmark coords)."""
    if gs.map_key == MAP_KEY_ELMS_LAB and starter_flag_set(gs):
        if (gs.player.x, gs.player.y) in (ELMS_LAB_EXIT, (5, 11)):
            return "down"
    if door is None:
        return None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN and (
        not has_starter(gs) or (_has_egg(gs) and not _egg_delivered(gs))
    ):
        pos = (gs.player.x, gs.player.y)
        approach = (door[0], door[1] + 1)
        if pos == approach:
            return "up"
        if pos[1] == approach[1] and pos[0] < approach[0]:
            return "right"
    return None


def blocked_lab_exit(gs: GameState) -> bool:
    """ROM gate: lab exit blocked until EVENT_GOT_A_POKEMON_FROM_ELM."""
    if gs.map_key != MAP_KEY_ELMS_LAB or starter_flag_set(gs):
        return False
    return (gs.player.x, gs.player.y) in ((4, 6), (5, 6))


def on_map_change(
    map_before: str,
    gs_after: GameState,
    state: dict[str, Any],
    *,
    action: str,
) -> None:
    if not action.startswith("navigate_"):
        return
    if map_before == MAP_KEY_NEW_BARK_TOWN and gs_after.map_key == MAP_KEY_ELMS_LAB:
        state["post_warp_wait_steps"] = max(
            state.get("post_warp_wait_steps", 0),
            POST_WARP_WAIT_TICKS // SCRIPT_WAIT_TICKS,
        )
    if map_before == MAP_KEY_ELMS_LAB and gs_after.map_key == MAP_KEY_NEW_BARK_TOWN:
        state["post_warp_wait_steps"] = max(
            state.get("post_warp_wait_steps", 0),
            POST_WARP_WAIT_TICKS // SCRIPT_WAIT_TICKS,
        )


def on_starter_quest_complete(state: dict[str, Any], gs: GameState) -> None:
    del gs
    state["starter_quest_complete"] = True


def starter_milestone(gs: GameState, maps_visited: list[str]) -> str | None:
    meta = _meta(gs)
    if _in_rival_battle(gs) and (meta.get("egg_delivered") or gs.map_key == MAP_KEY_ELMS_LAB):
        return MILESTONE_RIVAL_BATTLE
    if meta.get("egg_delivered"):
        return MILESTONE_EGG_DELIVERED
    if gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE and maps_visited.count(MAP_KEY_MR_POKEMONS_HOUSE) == 1:
        return MILESTONE_MR_POKEMON
    if starter_flag_set(gs) and gs.party_count >= 1:
        return MILESTONE_CHOSE_STARTER
    if gs.map_key == MAP_KEY_ELMS_LAB and maps_visited.count(MAP_KEY_ELMS_LAB) == 1:
        if MAP_KEY_NEW_BARK_TOWN in maps_visited:
            return MILESTONE_ENTERED_LAB
    return None


def format_map_context(gs: GameState) -> str:
    return f"{gs.map_key} {gs.player.map_name} ({gs.player.x},{gs.player.y})"