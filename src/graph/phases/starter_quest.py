"""Starter-quest phase: Elm's lab, egg delivery, and first rival battle."""

from __future__ import annotations

import os
from typing import Any

from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
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

NEW_BARK_LAB_WARP = (6, 3)
NEW_BARK_LAB_APPROACH = (6, 4)
ELMS_LAB_EXIT = (4, 11)
STARTER_BALL_TILE = (
    int(os.getenv("STARTER_BALL_X", "7")),
    int(os.getenv("STARTER_BALL_Y", "3")),
)
NEW_BARK_EAST_EXIT = (19, 12)
ROUTE_29_NORTH_GATE = (10, 5)
ROUTE_30_NORTH_GATE = (10, 3)
MR_POKEMON_DOOR = (5, 5)
ELM_DESK_TILE = (4, 2)

INDOOR_INTERACT_STUCK = int(os.getenv("INDOOR_INTERACT_STUCK", "2"))
POST_WARP_WAIT_TICKS = int(os.getenv("POST_WARP_WAIT_TICKS", "90"))
SCRIPT_WAIT_TICKS = int(os.getenv("SCRIPT_WAIT_TICKS", "45"))

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


def _has_starter(gs: GameState) -> bool:
    return bool(_meta(gs).get("has_starter"))


def _has_egg(gs: GameState) -> bool:
    return bool(_meta(gs).get("has_mystery_egg"))


def _egg_delivered(gs: GameState) -> bool:
    return bool(_meta(gs).get("egg_delivered"))


def _in_rival_battle(gs: GameState) -> bool:
    return gs.battle.in_battle and gs.battle.phase == BattlePhase.TRAINER


def is_satisfied(gs: GameState, state: dict[str, Any]) -> bool:
    """True once rival battle milestone persisted via starter_quest_complete flag."""
    del gs
    return bool(state.get("starter_quest_complete"))


def in_starter_quest(gs: GameState, state: dict[str, Any] | None = None) -> bool:
    """Active while post-house quest maps are incomplete."""
    state = state or {}
    if not state.get("house_exit_complete"):
        return False
    if state.get("starter_quest_complete"):
        return False
    if is_satisfied(gs, state):
        return False
    return gs.map_key in STARTER_QUEST_MAPS or not _egg_delivered(gs)


def lab_scene_pending(gs: GameState) -> bool:
    """Elm intro, ball choice, or aide potion script still running."""
    if gs.map_key != MAP_KEY_ELMS_LAB:
        return False
    return gs.in_text_box or bool(_meta(gs).get("in_script"))


def needs_lab_interaction(gs: GameState, state: dict[str, Any]) -> bool:
    if gs.map_key not in (MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE):
        return False
    if lab_scene_pending(gs):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and not _has_starter(gs)
        and (gs.player.x, gs.player.y) == STARTER_BALL_TILE
    ):
        return True
    if (
        gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
        and not _has_egg(gs)
        and (gs.player.x, gs.player.y) == MR_POKEMON_DOOR
    ):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and _has_egg(gs)
        and not _egg_delivered(gs)
        and (gs.player.x, gs.player.y) == ELM_DESK_TILE
    ):
        return True
    if _egg_delivered(gs) and gs.map_key == MAP_KEY_ELMS_LAB and not _in_rival_battle(gs):
        return True
    if gs.in_text_box and gs.map_key == MAP_KEY_ELMS_LAB:
        return True
    if state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK:
        last = state.get("last_action", "")
        return last.startswith("navigate_") and not last.endswith("_a")
    return False


def force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    return lab_scene_pending(gs) or (
        gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
        and not _has_egg(gs)
        and (gs.in_text_box or bool(_meta(gs).get("in_script")))
    )


def planner_allows_llm(gs: GameState, state: dict[str, Any]) -> bool:
    del state
    return gs.map_key not in (MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE)


def decompose_subgoals(gs: GameState) -> list[str] | None:
    if not _has_starter(gs):
        if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
            return ["Enter Elm's lab", "Listen to Elm", "Choose a starter"]
        if gs.map_key == MAP_KEY_ELMS_LAB:
            return ["Talk to Elm", "Pick a Poke Ball", "Receive Potion from aide"]
        return None
    if not _has_egg(gs):
        return ["Exit New Bark east", "Cross Route 29", "Visit Mr. Pokemon's house"]
    if not _egg_delivered(gs):
        return ["Return to New Bark", "Give Mystery Egg to Elm"]
    return ["Battle rival", "Heal if needed"]


def navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: dict[str, Any] | None = None,
) -> tuple[int, int] | None:
    del state
    map_key = map_key or gs.map_key

    if map_key == MAP_KEY_NEW_BARK_TOWN:
        if not _has_starter(gs):
            return NEW_BARK_LAB_WARP
        if _has_egg(gs) and not _egg_delivered(gs):
            return NEW_BARK_LAB_WARP
        if not _has_egg(gs):
            return NEW_BARK_EAST_EXIT
        return NEW_BARK_LAB_WARP

    if map_key == MAP_KEY_ELMS_LAB:
        if not _has_starter(gs):
            if lab_scene_pending(gs):
                return (gs.player.x, gs.player.y)
            return STARTER_BALL_TILE
        if _has_egg(gs) and not _egg_delivered(gs):
            return ELM_DESK_TILE
        if _has_starter(gs) and not _has_egg(gs):
            return ELMS_LAB_EXIT
        return (gs.player.x, gs.player.y)

    if map_key == MAP_KEY_ROUTE_29 and _has_starter(gs) and not _has_egg(gs):
        return ROUTE_29_NORTH_GATE if gs.player.y > ROUTE_29_NORTH_GATE[1] else ROUTE_29_NORTH_GATE

    if map_key == MAP_KEY_ROUTE_30 and _has_starter(gs) and not _has_egg(gs):
        return ROUTE_30_NORTH_GATE if gs.player.y > ROUTE_30_NORTH_GATE[1] else ROUTE_30_NORTH_GATE

    if map_key == MAP_KEY_MR_POKEMONS_HOUSE:
        if not _has_egg(gs):
            return MR_POKEMON_DOOR
        return (gs.player.x, gs.player.y + 2)

    if _has_egg(gs) and not _egg_delivered(gs):
        if map_key == MAP_KEY_NEW_BARK_TOWN:
            return NEW_BARK_LAB_WARP
        if map_key == MAP_KEY_ELMS_LAB:
            return ELM_DESK_TILE
        if map_key == MAP_KEY_ROUTE_29:
            return (0, gs.player.y)
        if map_key == MAP_KEY_ROUTE_30:
            return (gs.player.x, gs.player.y + 2)

    return None


def lab_entry_navigation_target(
    gs: GameState,
    *,
    door: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Route to the lab warp via the south approach tile when west of the door."""
    from src.graph.pathfinding import find_path

    door = door or NEW_BARK_LAB_WARP
    px, py = gs.player.x, gs.player.y
    approach = (door[0], door[1] + 1)
    if (px, py) in (door, approach):
        return door
    if py == approach[1] and px < approach[0]:
        return approach
    if find_path(px, py, approach[0], approach[1], map_key=gs.map_key):
        return approach
    return door


def door_exit_direction(gs: GameState, *, door: tuple[int, int] | None = None) -> str | None:
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN and (
        not _has_starter(gs) or (_has_egg(gs) and not _egg_delivered(gs))
    ):
        pos = (gs.player.x, gs.player.y)
        door = door or NEW_BARK_LAB_WARP
        approach = (door[0], door[1] + 1)
        if pos == approach:
            return "up"
        if pos[1] == approach[1] and pos[0] < approach[0]:
            return "right"
    if gs.map_key == MAP_KEY_ELMS_LAB and _has_starter(gs):
        if (gs.player.x, gs.player.y) in (ELMS_LAB_EXIT, (5, 11)):
            return "down"
    return None


def blocked_lab_exit(gs: GameState) -> bool:
    if gs.map_key != MAP_KEY_ELMS_LAB or _has_starter(gs):
        return False
    return (gs.player.x, gs.player.y) in ((4, 6), (5, 6))


def prefer_interact_candidate(gs: GameState) -> bool:
    if gs.in_text_box or lab_scene_pending(gs):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and not _has_starter(gs)
        and (gs.player.x, gs.player.y) == STARTER_BALL_TILE
    ):
        return True
    if (
        gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
        and not _has_egg(gs)
        and (gs.player.x, gs.player.y) == MR_POKEMON_DOOR
    ):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and _has_egg(gs)
        and not _egg_delivered(gs)
        and (gs.player.x, gs.player.y) == ELM_DESK_TILE
    ):
        return True
    return False


def stuck_interact_fallback(gs: GameState, state: dict[str, Any]) -> bool:
    return (
        gs.map_key in (MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE)
        and state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    )


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
    if meta.get("has_starter") and gs.party_count >= 1:
        return MILESTONE_CHOSE_STARTER
    if gs.map_key == MAP_KEY_ELMS_LAB and maps_visited.count(MAP_KEY_ELMS_LAB) == 1:
        if MAP_KEY_NEW_BARK_TOWN in maps_visited:
            return MILESTONE_ENTERED_LAB
    return None


def format_map_context(gs: GameState) -> str:
    return f"{gs.map_key} {gs.player.map_name} ({gs.player.x},{gs.player.y})"