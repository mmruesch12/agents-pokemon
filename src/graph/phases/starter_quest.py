"""Starter-quest phase: Elm's lab, egg delivery, and first rival battle."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
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

NEW_BARK_LAB_WARP = (6, 3)
NEW_BARK_LAB_APPROACH = (6, 4)
ELMS_LAB_EXIT = (4, 11)
STARTER_BALL_TILE = (
    int(os.getenv("STARTER_BALL_X", "7")),
    int(os.getenv("STARTER_BALL_Y", "3")),
)
STARTER_BALL_TILES = ((6, 3), (7, 3), (8, 3))
STARTER_BALL_APPROACH = (5, 3)
MR_POKEMON_DOOR = (5, 5)
ELM_DESK_TILE = (4, 2)
ELM_DESK_APPROACH = (4, 3)
FACING_TO_DIRECTION = {0: "down", 4: "up", 8: "left", 12: "right"}
VALID_PLAYER_FACING = frozenset(FACING_TO_DIRECTION)


def player_facing_direction(gs: GameState) -> str | None:
    """Map WRAM facing byte to a direction; None when invalid (e.g. mid-turn)."""
    return FACING_TO_DIRECTION.get(gs.player.facing)


def facing_is_valid(gs: GameState) -> bool:
    return gs.player.facing in VALID_PLAYER_FACING

INDOOR_INTERACT_STUCK = int(os.getenv("INDOOR_INTERACT_STUCK", "2"))
LAB_PARTY_STALL_STEPS = int(os.getenv("LAB_PARTY_STALL_STEPS", "8"))
LAB_DESK_INTERACT_CAP = int(os.getenv("LAB_DESK_INTERACT_CAP", "12"))
POST_WARP_WAIT_TICKS = int(os.getenv("POST_WARP_WAIT_TICKS", "90"))
SCRIPT_WAIT_TICKS = int(os.getenv("SCRIPT_WAIT_TICKS", "45"))


class LabPhase(str, Enum):
    DESK = "desk"
    WAIT_SCRIPT = "wait_script"
    BALL_APPROACH = "ball_approach"
    BALL_INTERACT = "ball_interact"
    EXIT = "exit"


@dataclass(frozen=True)
class LabDirective:
    phase: LabPhase
    nav_target: tuple[int, int]
    prefer_interact: bool = False
    force_interact: bool = False
    face_before_interact: str | None = None

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
    """ROM event flag: player chose a starter from Elm (may lead party_count)."""
    return bool(_meta(gs).get("has_starter"))


def has_starter(gs: GameState) -> bool:
    """True when Elm starter flag is set and party actually has a Pokemon."""
    return starter_flag_set(gs) and gs.party_count >= 1


def _has_starter(gs: GameState) -> bool:
    return has_starter(gs)


def starter_pick_dialog_active(gs: GameState) -> bool:
    """Nickname / confirmation dialog still open after the starter event flag."""
    return (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_flag_set(gs)
        and not has_starter(gs)
        and lab_scene_pending(gs)
    )


def _player_tile(gs: GameState) -> tuple[int, int]:
    return (gs.player.x, gs.player.y)


def is_on_starter_ball_tile(gs: GameState) -> bool:
    return _player_tile(gs) in STARTER_BALL_TILES


def is_adjacent_to_starter_ball(gs: GameState) -> bool:
    px, py = gs.player.x, gs.player.y
    for bx, by in STARTER_BALL_TILES:
        if abs(px - bx) + abs(py - by) == 1:
            return True
    return False


def can_interact_starter_ball(gs: GameState) -> bool:
    return (
        gs.map_key == MAP_KEY_ELMS_LAB
        and not starter_flag_set(gs)
        and not _has_starter(gs)
        and (is_on_starter_ball_tile(gs) or is_adjacent_to_starter_ball(gs))
    )


def starter_ball_face_direction(gs: GameState) -> str | None:
    """Direction to face the nearest starter ball for A-button interaction."""
    if not can_interact_starter_ball(gs):
        return None
    px, py = gs.player.x, gs.player.y
    nearest: tuple[int, int] | None = None
    best_dist = 999
    for bx, by in STARTER_BALL_TILES:
        dist = abs(px - bx) + abs(py - by)
        if dist < best_dist:
            best_dist = dist
            nearest = (bx, by)
    if nearest is None or best_dist == 0:
        return None
    bx, by = nearest
    if bx > px:
        return "right"
    if bx < px:
        return "left"
    if by > py:
        return "down"
    if by < py:
        return "up"
    return None


def _starter_ball_approach_tile(gs: GameState) -> tuple[int, int]:
    """Walkable tile adjacent to a ball — interact from the side, not on the ball."""
    if can_interact_starter_ball(gs):
        return _player_tile(gs)
    return STARTER_BALL_APPROACH


def is_at_elm_desk(gs: GameState) -> bool:
    return gs.map_key == MAP_KEY_ELMS_LAB and _player_tile(gs) in (
        ELM_DESK_TILE,
        (5, 2),
        ELM_DESK_APPROACH,
    )


def _past_elm_desk_intro(gs: GameState) -> bool:
    """Player at the ball approach tile or adjacent implies desk intro finished."""
    if gs.map_key != MAP_KEY_ELMS_LAB or _has_starter(gs):
        return False
    if is_at_elm_desk(gs):
        return False
    if can_interact_starter_ball(gs):
        return True
    return _player_tile(gs) == STARTER_BALL_APPROACH


def desk_dialog_done(gs: GameState, state: dict[str, Any]) -> bool:
    """True once Elm desk script was seen and cleared (ROM-derived)."""
    if _has_starter(gs):
        return True
    if state.get("lab_desk_dialog_done"):
        return True
    if state.get("lab_desk_interact_count", 0) >= LAB_DESK_INTERACT_CAP:
        return True
    if _past_elm_desk_intro(gs):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and not lab_scene_pending(gs)
        and state.get("lab_desk_interact_count", 0) >= 1
        and not is_at_elm_desk(gs)
    ):
        return True
    return False


def update_lab_rom_observables(gs: GameState, state: dict[str, Any]) -> None:
    """Track ROM-derived lab progress and party-stall steps."""
    if gs.map_key != MAP_KEY_ELMS_LAB or starter_flag_set(gs):
        for key in (
            "lab_desk_script_seen",
            "lab_desk_dialog_done",
            "lab_steps_without_party",
            "lab_stall_position",
            "lab_party_count_snapshot",
        ):
            state.pop(key, None)
        return
    if is_at_elm_desk(gs) and lab_scene_pending(gs):
        state["lab_desk_script_seen"] = True
    elif state.get("lab_desk_script_seen") and not lab_scene_pending(gs):
        if not state.get("lab_desk_dialog_done"):
            state["lab_steps_without_party"] = 0
            state["lab_stall_position"] = None
        state["lab_desk_dialog_done"] = True
    party = gs.party_count
    if party > 0:
        state["lab_steps_without_party"] = 0
        state["lab_stall_position"] = None
        state["stuck_count"] = 0
        return
    directive = resolve_lab_pre_starter(gs, state)
    if directive is None or directive.phase in (
        LabPhase.DESK,
        LabPhase.WAIT_SCRIPT,
        LabPhase.BALL_INTERACT,
    ):
        state["lab_steps_without_party"] = 0
        state["lab_stall_position"] = gs.position_key
        return
    if can_interact_starter_ball(gs) and desk_dialog_done(gs, state):
        state["lab_steps_without_party"] = 0
        state["lab_stall_position"] = gs.position_key
        return
    pos = gs.position_key
    if state.get("lab_stall_position") == pos:
        state["lab_steps_without_party"] = state.get("lab_steps_without_party", 0) + 1
    else:
        state["lab_stall_position"] = pos
        state["lab_steps_without_party"] = 0
    state["lab_party_count_snapshot"] = party


def lab_party_stall_detected(gs: GameState, state: dict[str, Any]) -> bool:
    """Steps in lab without gaining a party member at the same tile."""
    if gs.map_key != MAP_KEY_ELMS_LAB or starter_flag_set(gs):
        return False
    if lab_scene_pending(gs) or lab_ball_picking_active(gs, state):
        return False
    if can_interact_starter_ball(gs) and desk_dialog_done(gs, state):
        return False
    return state.get("lab_steps_without_party", 0) >= LAB_PARTY_STALL_STEPS


def _should_leave_elm_desk(gs: GameState, state: dict[str, Any]) -> bool:
    """Desk intro finished or stale script — route toward starter balls."""
    desk_interacts = state.get("lab_desk_interact_count", 0)
    stale_script_escape = (
        desk_interacts >= 2
        and lab_scene_pending(gs)
        and not state.get("lab_desk_script_seen")
    )
    return (
        (desk_dialog_done(gs, state) and not lab_scene_pending(gs))
        or stale_script_escape
        or _interact_stuck(state)
    ) and not _navigation_stuck(state)


def lab_desk_intro_active(gs: GameState, state: dict[str, Any]) -> bool:
    """At Elm's desk before ROM marks intro complete — avoid navigate/replan loops."""
    if gs.map_key != MAP_KEY_ELMS_LAB or _has_starter(gs):
        return False
    return is_at_elm_desk(gs) and not desk_dialog_done(gs, state)


def lab_ball_picking_active(gs: GameState, state: dict[str, Any]) -> bool:
    """At the ball row advancing pick dialog — suppress navigate/replan loops."""
    if gs.map_key != MAP_KEY_ELMS_LAB or has_starter(gs):
        return False
    if starter_pick_dialog_active(gs):
        return True
    if not desk_dialog_done(gs, state) or not can_interact_starter_ball(gs):
        return False
    if lab_scene_pending(gs):
        return True
    if state.get("last_action", "").startswith("interact_"):
        return True
    directive = resolve_lab_pre_starter(gs, state)
    if directive is None or directive.phase != LabPhase.BALL_INTERACT:
        return False
    if directive.force_interact:
        return True
    return facing_toward_ball(gs)


def resolve_lab_pre_starter(
    gs: GameState, state: dict[str, Any]
) -> LabDirective | None:
    """Single resolver for pre-starter Elm's Lab routing."""
    if gs.map_key != MAP_KEY_ELMS_LAB or has_starter(gs) or starter_flag_set(gs):
        if starter_pick_dialog_active(gs):
            return LabDirective(
                LabPhase.BALL_INTERACT,
                _player_tile(gs),
                prefer_interact=True,
                force_interact=True,
            )
        return None
    pos = _player_tile(gs)

    if desk_dialog_done(gs, state) and not lab_scene_pending(gs):
        if can_interact_starter_ball(gs):
            face = starter_ball_face_direction(gs)
            facing_ok = face is None or player_facing_direction(gs) == face
            if lab_scene_pending(gs):
                return LabDirective(
                    LabPhase.BALL_INTERACT,
                    pos,
                    prefer_interact=True,
                    force_interact=True,
                )
            if (
                not facing_ok
                and face is not None
                and not ball_face_turn_exhausted(gs, state)
            ):
                return LabDirective(
                    LabPhase.BALL_INTERACT,
                    pos,
                    face_before_interact=face,
                )
            return LabDirective(
                LabPhase.BALL_INTERACT,
                pos,
                prefer_interact=True,
                force_interact=ball_face_turn_exhausted(gs, state),
            )
        return LabDirective(LabPhase.BALL_APPROACH, _starter_ball_approach_tile(gs))

    if is_at_elm_desk(gs):
        if lab_scene_pending(gs):
            return LabDirective(
                LabPhase.WAIT_SCRIPT,
                pos,
                prefer_interact=True,
                force_interact=True,
            )
        if _should_leave_elm_desk(gs, state):
            return LabDirective(LabPhase.BALL_APPROACH, STARTER_BALL_APPROACH)
        return LabDirective(
            LabPhase.DESK,
            ELM_DESK_TILE,
            prefer_interact=True,
            force_interact=not desk_dialog_done(gs, state),
        )

    if lab_scene_pending(gs):
        return LabDirective(
            LabPhase.WAIT_SCRIPT,
            pos,
            prefer_interact=True,
            force_interact=True,
        )
    return LabDirective(LabPhase.DESK, ELM_DESK_TILE)


def facing_toward_ball(gs: GameState) -> bool:
    face = starter_ball_face_direction(gs)
    if face is None:
        return True
    return player_facing_direction(gs) == face


def ready_for_ball_interact(gs: GameState) -> bool:
    return can_interact_starter_ball(gs) and (
        lab_scene_pending(gs) or facing_toward_ball(gs)
    )


def _navigation_stuck(state: dict[str, Any]) -> bool:
    """Failed movement at the same tile — prefer navigator over forced interact."""
    stuck = state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    last = state.get("last_action", "")
    return stuck and last.startswith("navigate_") and not last.endswith("_a")


def ball_face_turn_exhausted(gs: GameState, state: dict[str, Any]) -> bool:
    """Facing toward the ball succeeded, or turn attempts should yield to interact."""
    face = starter_ball_face_direction(gs)
    if face is None:
        return True
    if player_facing_direction(gs) == face:
        return True
    last = state.get("last_action", "")
    if last.startswith("interact_") and can_interact_starter_ball(gs):
        return True
    if state.get("lab_steps_without_party", 0) >= LAB_PARTY_STALL_STEPS:
        return True
    if not facing_is_valid(gs):
        return state.get("stuck_count", 0) >= 1
    return (
        state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
        and last.startswith("navigate_")
    )


def _interact_stuck(state: dict[str, Any]) -> bool:
    """Repeated unproductive interacts — let navigator face/reposition or replan."""
    stuck = state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    last = state.get("last_action", "")
    return stuck and last.startswith("interact_")


def _subgoal_index(gs: GameState, state: dict[str, Any]) -> int:
    if starter_flag_set(gs) and not _has_egg(gs):
        return 2
    if not desk_dialog_done(gs, state) and is_at_elm_desk(gs):
        return 0
    directive = resolve_lab_pre_starter(gs, state)
    if directive is None:
        return 0
    if directive.phase == LabPhase.WAIT_SCRIPT:
        if desk_dialog_done(gs, state) or can_interact_starter_ball(gs):
            return 1
        return 0
    if directive.phase == LabPhase.DESK:
        return 0
    if directive.phase in (LabPhase.BALL_APPROACH, LabPhase.BALL_INTERACT):
        return 1
    return 0


def ensure_house_exit_complete(gs: GameState, state: dict[str, Any]) -> None:
    """Bedroom-start may reach lab before the New Bark milestone is recorded."""
    if state.get("house_exit_complete"):
        return
    maps = state.get("maps_visited", [])
    from_house = (
        MAP_KEY_PLAYERS_HOUSE_1F in maps or MAP_KEY_PLAYERS_HOUSE_2F in maps
    )
    if from_house and gs.map_key in STARTER_QUEST_MAPS:
        state["house_exit_complete"] = True


def sync_subgoals(gs: GameState, state: dict[str, Any]) -> None:
    """Refresh starter-quest subgoals once house exit is complete."""
    ensure_house_exit_complete(gs, state)
    if not state.get("house_exit_complete"):
        return
    subgoals = decompose_subgoals(gs)
    if not subgoals:
        return
    state["subgoals"] = subgoals
    idx = min(_subgoal_index(gs, state), len(subgoals) - 1)
    state["active_subgoal"] = subgoals[idx]


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
    directive = resolve_lab_pre_starter(gs, state)
    if directive is not None:
        if directive.force_interact:
            return True
        if directive.phase == LabPhase.BALL_INTERACT:
            if directive.face_before_interact is not None:
                return ball_face_turn_exhausted(gs, state)
            return True
        if directive.prefer_interact and not _navigation_stuck(state):
            return True
        if lab_party_stall_detected(gs, state):
            return False
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
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_flag_set(gs)
        and not _has_egg(gs)
        and gs.player.y >= 7
        and (gs.in_text_box or lab_scene_pending(gs))
    ):
        return True
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_flag_set(gs)
        and not _has_egg(gs)
        and gs.player.y >= 7
        and state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK
    ):
        return True
    if state.get("stuck_count", 0) >= INDOOR_INTERACT_STUCK:
        last = state.get("last_action", "")
        if not (last.startswith("navigate_") and not last.endswith("_a")):
            return False
        if gs.map_key == MAP_KEY_ELMS_LAB and not _has_starter(gs):
            return lab_scene_pending(gs) or can_interact_starter_ball(gs)
        return True
    return False


def force_interactor(gs: GameState, state: dict[str, Any]) -> bool:
    directive = resolve_lab_pre_starter(gs, state)
    if directive is not None:
        return directive.force_interact
    if lab_scene_pending(gs):
        return True
    return (
        gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
        and not _has_egg(gs)
        and (gs.in_text_box or bool(_meta(gs).get("in_script")))
    )


def planner_allows_llm(gs: GameState, state: dict[str, Any]) -> bool:
    if gs.map_key not in (MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE):
        return True
    return state.get("stuck_count", 0) >= 3


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
    state = state or {}
    map_key = map_key or gs.map_key

    if map_key == MAP_KEY_NEW_BARK_TOWN:
        if not _has_starter(gs):
            return NEW_BARK_LAB_WARP
        if _has_egg(gs) and not _egg_delivered(gs):
            return NEW_BARK_LAB_WARP
        if not _has_egg(gs):
            return None
        return NEW_BARK_LAB_WARP

    if map_key == MAP_KEY_ELMS_LAB:
        if not starter_flag_set(gs):
            directive = resolve_lab_pre_starter(gs, state)
            if directive is not None:
                return directive.nav_target
        if _has_egg(gs) and not _egg_delivered(gs):
            return ELM_DESK_TILE
        if starter_flag_set(gs) and not _has_egg(gs):
            return ELMS_LAB_EXIT
        return (gs.player.x, gs.player.y)

    if map_key == MAP_KEY_ROUTE_29 and _has_starter(gs) and not _has_egg(gs):
        return None

    if map_key == MAP_KEY_ROUTE_30 and _has_starter(gs) and not _has_egg(gs):
        return None

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
    if gs.map_key == MAP_KEY_ELMS_LAB and starter_flag_set(gs):
        if (gs.player.x, gs.player.y) in (ELMS_LAB_EXIT, (5, 11)):
            return "down"
    return None


def blocked_lab_exit(gs: GameState) -> bool:
    if gs.map_key != MAP_KEY_ELMS_LAB or starter_flag_set(gs):
        return False
    return (gs.player.x, gs.player.y) in ((4, 6), (5, 6))


def prefer_interact_candidate(
    gs: GameState,
    state: dict[str, Any] | None = None,
) -> bool:
    state = state or {}
    directive = resolve_lab_pre_starter(gs, state)
    if directive is not None:
        if directive.force_interact:
            return True
        if directive.phase == LabPhase.BALL_INTERACT:
            if directive.face_before_interact is not None:
                return ball_face_turn_exhausted(gs, state)
            return True
        if directive.prefer_interact and not _navigation_stuck(state):
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
    if state.get("stuck_count", 0) < INDOOR_INTERACT_STUCK:
        return False
    directive = resolve_lab_pre_starter(gs, state)
    if directive is not None:
        return directive.phase == LabPhase.BALL_INTERACT and can_interact_starter_ball(gs)
    return gs.map_key in (MAP_KEY_ELMS_LAB, MAP_KEY_MR_POKEMONS_HOUSE)


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