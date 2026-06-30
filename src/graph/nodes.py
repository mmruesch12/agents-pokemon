"""Multi-agent graph nodes: Supervisor, Planner, Navigator, Battler, Critic, Memory."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.emulator.bootstrap import needs_bootstrap, pick_bootstrap_button
from src.graph.generic_interact import (
    generic_force_interactor,
    generic_is_interact_needed,
    generic_prefer_interact_candidate,
    generic_stuck_interact_fallback,
)
from src.graph.navigation_resolve import resolve_navigation_target
from src.graph.llm import llm_battle, llm_navigate, llm_plan
from src.graph.pathfinding import (
    MAP_GRIDS,
    _is_walkable,
    direction_toward,
    find_path,
    record_session_walkable,
    session_walkable_for_map,
)
from src.graph.phases import early_progression, house_exit, starter_quest
from src.graph.state import AgentState, update_game_state
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_INTERIOR_ID,
    MR_POKEMONS_HOUSE_ENTRANCE_ID,
    apply_landmark_discovery,
    discover_elms_lab_landmarks,
    discover_map_visit_landmark,
    discover_mr_pokemon_entrance_landmark,
    discover_quest_transition_landmarks,
    find_landmark,
    format_landmarks_for_prompt,
    landmark_coords,
    landmark_known,
    memory_data_dir,
    parse_position_key,
    retrieve_landmarks_from_state,
)
from src.memory.long_term_memory import LongTermMemory
from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    MAP_KEY_ROUTE_29,
    PLAYERS_HOUSE_1F_DOOR,
)
from src.state.models import GameState
from src.state.script_constants import (
    SCRIPT_FLAG_SCRIPT_RUNNING,
    SCRIPT_READ,
    SCRIPT_WAIT,
    SCRIPT_WAIT_MOVEMENT,
    joypad_input_blocked,
)

logger = logging.getLogger(__name__)

STUCK_THRESHOLD = int(os.getenv("STUCK_THRESHOLD", "10"))
STUCK_ARBITRATION_THRESHOLD = int(os.getenv("STUCK_ARBITRATION_THRESHOLD", "2"))
NAVIGATION_REPEAT_THRESHOLD = int(os.getenv("NAVIGATION_REPEAT_THRESHOLD", "3"))
INTERACT_HOLD_FRAMES = int(os.getenv("INTERACT_HOLD_FRAMES", "30"))
SCRIPT_WAIT_TICKS = int(os.getenv("SCRIPT_WAIT_TICKS", "45"))

_DIRECTION_DELTA = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
_OPPOSITE_DIRECTIONS = frozenset({("left", "right"), ("right", "left"), ("up", "down"), ("down", "up")})

def _long_term_memory() -> LongTermMemory:
    return LongTermMemory(data_dir=memory_data_dir())


def score_visit_aware_candidate(
    direction: str,
    gs: GameState,
    state: AgentState,
) -> float:
    """Prefer unvisited adjacent tiles; penalize immediate backtrack oscillation."""
    if direction == "a":
        return 0.0
    dx, dy = _DIRECTION_DELTA.get(direction, (0, 0))
    nx, ny = gs.player.x + dx, gs.player.y + dy
    pos_key = f"{gs.map_key}:{nx}:{ny}"
    visited = set(state.get("visited_positions", []))
    score = 2.0 if pos_key not in visited else -1.0
    nav_history = [
        entry.split(":")[1].split("@")[0]
        for entry in state.get("short_term_history", [])
        if entry.startswith("navigate:")
    ]
    if len(nav_history) >= 2:
        last_dir = nav_history[-1]
        prev_dir = nav_history[-2]
        if (prev_dir, direction) in _OPPOSITE_DIRECTIONS or (last_dir, direction) in _OPPOSITE_DIRECTIONS:
            score -= 1.5
    return score


def _parse_history_entry(item: str) -> tuple[str, str, str | None] | None:
    """Return (kind, payload, position) for navigate:/interact: history entries."""
    if "@" not in item or ":" not in item:
        return None
    action, pos = item.split("@", 1)
    kind, payload = action.split(":", 1)
    return kind, payload, pos


def repeating_nav_direction(history: list[str], *, min_count: int | None = None) -> str | None:
    """Direction repeated at the same tile (e.g. teacher gate blocking east)."""
    min_count = NAVIGATION_REPEAT_THRESHOLD if min_count is None else min_count
    if len(history) < min_count:
        return None
    parsed: list[tuple[str, str]] = []
    for item in history[-min_count:]:
        entry = _parse_history_entry(item)
        if entry is None or entry[0] != "navigate":
            return None
        parsed.append((entry[1], entry[2] or ""))
    positions = {pos for _, pos in parsed}
    directions = [direction for direction, _ in parsed]
    if len(positions) != 1 or len(set(directions)) != 1:
        return None
    return directions[0]


def navigation_repeat_detected(
    history: list[str],
    *,
    min_count: int | None = None,
) -> bool:
    return repeating_nav_direction(history, min_count=min_count) is not None


def navigation_arbitration_active(stuck_count: int, state: AgentState) -> bool:
    """True when navigator should override blind path[0] (M11)."""
    history = state.get("short_term_history", [])
    return stuck_count >= STUCK_ARBITRATION_THRESHOLD or navigation_repeat_detected(history)


def walkable_cardinal_candidates(gs: GameState, state: AgentState | None = None) -> list[str]:
    """Adjacent walkable directions from the pathfinding grid (M4 loop expansion)."""
    grid = MAP_GRIDS.get(gs.map_key)
    session_walkable = session_walkable_for_map(state, gs.map_key)
    candidates: list[str] = []
    for direction, (dx, dy) in _DIRECTION_DELTA.items():
        nx, ny = gs.player.x + dx, gs.player.y + dy
        if direction == "up" and _blocked_stairs_up(gs):
            continue
        if _is_walkable(grid, nx, ny, session_walkable=session_walkable):
            candidates.append(direction)
    return candidates


def expand_candidates_on_stuck(
    gs: GameState,
    candidates: list[str],
    state: AgentState,
    *,
    stuck_count: int,
) -> list[str]:
    """Add walkable cardinals when stuck or repeating so visit-aware can break loops."""
    if not navigation_arbitration_active(stuck_count, state):
        return candidates
    merged = list(candidates)
    for direction in walkable_cardinal_candidates(gs, state):
        if direction not in merged:
            merged.append(direction)
    return list(dict.fromkeys(merged))


def reorder_candidates_visit_aware(
    gs: GameState,
    candidates: list[str],
    state: AgentState,
) -> list[str]:
    """Stable reorder: higher visit-aware score first."""
    ranked = sorted(
        candidates,
        key=lambda direction: score_visit_aware_candidate(direction, gs, state),
        reverse=True,
    )
    return list(dict.fromkeys(ranked))


def visit_aware_path_step(
    path: list[str],
    gs: GameState,
    state: AgentState,
) -> str | None:
    """Best visit-aware step from an A* path prefix (M4 normal-path bias)."""
    if not path:
        return None
    ranked = reorder_candidates_visit_aware(gs, path[:3], state)
    return ranked[0] if ranked else path[0]


_FACING_TO_DIRECTION = {0: "down", 4: "up", 8: "left", 12: "right"}


def select_navigation_action(
    *,
    door_exit: str | None,
    path: list[str],
    llm_choice: str | None,
    candidates: list[str],
    stuck_count: int,
    gs: GameState,
    state: AgentState,
    target: tuple[int, int],
) -> str:
    """Pick direction: door priority, stuck override, visit-aware path, LLM, fallback."""
    if door_exit:
        return door_exit
    arbitrate = navigation_arbitration_active(stuck_count, state)
    if arbitrate and llm_choice and llm_choice in candidates:
        return llm_choice
    if arbitrate:
        repeat_dir = repeating_nav_direction(state.get("short_term_history", []))
        pool = [c for c in candidates if c not in {"a", repeat_dir}] or candidates
        ranked = reorder_candidates_visit_aware(gs, pool, state)
        if ranked and ranked[0] != "a":
            return ranked[0]
    if path:
        return visit_aware_path_step(path, gs, state) or path[0]
    if llm_choice and llm_choice in candidates and llm_choice != "a":
        return llm_choice
    toward = direction_toward(gs.player.x, gs.player.y, target[0], target[1])
    if toward != "a":
        return toward
    for step in candidates:
        if step != "a":
            return step
    return "down"


def _capture_stuck_episode(state: AgentState, gs: GameState) -> None:
    try:
        _long_term_memory().capture_stuck_episode(state, gs)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not capture stuck episode: %s", exc)


def _attach_landmark_context(state: AgentState, gs: GameState) -> list[dict[str, Any]]:
    landmarks = list(state.get("known_landmarks", []))
    query = f"{gs.map_key} {gs.player.map_name} {state.get('active_subgoal', '')}"
    relevant = retrieve_landmarks_from_state(landmarks, query, k=3)
    formatted = format_landmarks_for_prompt(relevant)
    if formatted:
        retrievals = list(state.get("memory_retrievals", []))
        if formatted not in retrievals:
            retrievals.append(formatted)
        state["memory_retrievals"] = retrievals[-5:]
    return relevant


def _persist_landmark_discoveries(state: AgentState, discoveries: list[dict[str, Any]]) -> None:
    if not discoveries:
        return
    apply_landmark_discovery(state, discoveries)
    try:
        memory = _long_term_memory()
        for landmark in discoveries:
            memory.add_landmark(landmark)
            logger.info(
                "Landmark discovered: %s at %s (%s,%s)",
                landmark.get("name"),
                landmark.get("map_key"),
                landmark.get("x"),
                landmark.get("y"),
            )
    except OSError as exc:
        logger.warning("Could not persist landmarks: %s", exc)


EARLY_GAME_OBJECTIVES = {
    MAP_KEY_PLAYERS_HOUSE_2F: "Leave bedroom via stairs, talk to Mom on 1F, then head to Professor Elm",
    MAP_KEY_PLAYERS_HOUSE_1F: "Talk to Mom and leave through the front door to New Bark Town",
    MAP_KEY_NEW_BARK_TOWN: "Visit Professor Elm's lab and choose a starter Pokemon",
    "24:5": "Talk to Elm, choose a starter Pokemon, receive Potion",
    MAP_KEY_ROUTE_29: "Travel north through Route 29 toward Cherrygrove City",
    MAP_KEY_CHERRYGROVE_CITY: "Explore Cherrygrove and continue toward Violet City",
    "26:10": "Talk to Mr. Pokemon and receive the Mystery Egg from Oak",
    "1:2": "Visit Pokemon Center and continue toward Violet City",
    "1:4": "Challenge Violet City gym (first badge goal)",
}


def _hold_phase_satisfied(gs: GameState, state: AgentState) -> bool:
    """Terminal idle only when the active early-game phase goal is complete."""
    if not state.get("house_exit_complete"):
        return house_exit.is_satisfied(gs, state)
    if not state.get("starter_quest_complete"):
        return starter_quest.is_satisfied(gs, state)
    return early_progression.is_satisfied(gs, state)


def supervisor_node(state: AgentState) -> AgentState:
    """Route to appropriate specialist based on game phase."""
    gs = GameState.model_validate(state.get("game_state", {}))

    if needs_bootstrap(gs, state):
        state["next_node"] = "bootstrap"
        state["phase"] = "bootstrap"
    elif _hold_phase_satisfied(gs, state):
        state["next_node"] = "idle"
        if not state.get("house_exit_complete"):
            state["phase"] = "house_exit_done"
        elif state.get("starter_quest_complete"):
            state["phase"] = "early_progression_done"
        else:
            state["phase"] = "starter_quest_done"
    elif gs.battle.in_battle:
        state["next_node"] = "battler"
        state["phase"] = "battle"
    elif needs_script_wait(gs, state):
        state["next_node"] = "waiter"
        state["phase"] = "wait"
    elif state.get("should_replan"):
        state["next_node"] = "planner"
    elif needs_interaction(gs, state):
        state["next_node"] = "interactor"
        state["phase"] = "interact"
    elif house_exit.force_interactor(gs, state) or generic_force_interactor(gs, state):
        state["next_node"] = "interactor"
        state["phase"] = "interact"
    elif state.get("stuck_count", 0) >= STUCK_THRESHOLD:
        state["next_node"] = "planner"
        state["should_replan"] = True
    elif state.get("phase") == "plan":
        state["next_node"] = "planner"
    else:
        state["next_node"] = "navigator"

    if state["next_node"] == "navigator":
        if state.get("starter_quest_complete") and not early_progression.is_satisfied(gs, state):
            state["phase"] = "early_progression"
        elif state.get("house_exit_complete") and not state.get("starter_quest_complete"):
            state["phase"] = "starter_quest"
    elif state["next_node"] == "planner" and state.get("starter_quest_complete"):
        state["phase"] = "early_progression"
    elif state["next_node"] == "battler" and state.get("starter_quest_complete"):
        state["phase"] = "early_progression"

    logger.debug("Supervisor routing to %s", state["next_node"])
    return state


def _valid_script_mode(mode: int) -> bool:
    return mode in (SCRIPT_READ, SCRIPT_WAIT_MOVEMENT, SCRIPT_WAIT)


def needs_script_wait(gs: GameState, state: dict | None = None) -> bool:
    """True when a map script is running movement/timing steps (no button input)."""
    state = state or {}
    if gs.battle.in_battle or needs_bootstrap(gs, state):
        return False
    meta = gs.raw_metadata or {}
    mode = meta.get("script_mode", 0)
    script_active = bool(meta.get("script_flags", 0) & SCRIPT_FLAG_SCRIPT_RUNNING)
    joypad_disable = meta.get("joypad_disable", 0)
    if state.get("post_warp_wait_steps", 0) > 0:
        return True
    if not _valid_script_mode(mode):
        return False
    if mode in (SCRIPT_WAIT_MOVEMENT, SCRIPT_WAIT) and script_active:
        return True
    if mode == SCRIPT_READ and joypad_input_blocked(joypad_disable) and script_active:
        return True
    return False


def needs_interaction(gs: GameState, state: dict | None = None) -> bool:
    """True when ROM signals expect A/B dialog input instead of movement."""
    state = state or {}
    if gs.battle.in_battle or needs_bootstrap(gs, state) or needs_script_wait(gs, state):
        return False
    starter_quest.ensure_house_exit_complete(gs, state)
    if house_exit.needs_house_interaction(gs, state):
        return True
    return generic_is_interact_needed(gs, state)


def waiter_node(state: AgentState) -> AgentState:
    """Advance scripted movement by ticking frames without joypad input."""
    gs = GameState.model_validate(state.get("game_state", {}))
    remaining = state.get("post_warp_wait_steps", 0)
    if remaining > 0:
        state["post_warp_wait_steps"] = remaining - 1
    state["last_action"] = "wait_script"
    state["last_action_result"] = {
        "script_mode": (gs.raw_metadata or {}).get("script_mode"),
        "script_running": (gs.raw_metadata or {}).get("script_running"),
        "post_warp_remaining": state.get("post_warp_wait_steps", 0),
    }
    state["position_before_action"] = gs.position_key
    state["facing_before_action"] = gs.player.facing
    state["next_node"] = "critic"
    return state


def _lab_interact_button_only(gs: GameState, state: AgentState) -> bool:
    """Gen 2 lab dialogs break on B — prefer A in Elm's lab during scripts."""
    if gs.map_key != MAP_KEY_ELMS_LAB:
        return False
    return generic_is_interact_needed(gs, state)


def interactor_node(state: AgentState) -> AgentState:
    """Advance dialog and scripted indoor scenes with A/B."""
    gs = GameState.model_validate(state.get("game_state", {}))
    idx = state.get("interact_action_index", 0)
    if _lab_interact_button_only(gs, state):
        button = "a"
    else:
        button = "a" if idx % 8 != 7 else "b"
    state["interact_action_index"] = idx + 1
    state["last_action"] = f"interact_{button}"
    state["last_action_result"] = {"button": button, "interact_index": idx}
    state["position_before_action"] = gs.position_key
    state["facing_before_action"] = gs.player.facing
    history = list(state.get("short_term_history", []))
    history.append(f"interact:{button}@{gs.player.x},{gs.player.y}")
    state["short_term_history"] = history[-20:]
    state["next_node"] = "critic"
    return state


def bootstrap_node(state: AgentState) -> AgentState:
    """Press through title screens, dialogs, name entry, and clock setup."""
    gs = GameState.model_validate(state.get("game_state", {}))
    idx = state.get("bootstrap_action_index", 0)
    loaded_map = None
    if gs.player.map_group or gs.player.map_id:
        loaded_map = (gs.player.map_group, gs.player.map_id)
    button = pick_bootstrap_button(idx, loaded_map=loaded_map)
    state["bootstrap_action_index"] = idx + 1
    state["last_action"] = f"bootstrap_{button}"
    state["last_action_result"] = {"button": button, "bootstrap_index": idx}
    state["position_before_action"] = gs.position_key
    history = list(state.get("short_term_history", []))
    history.append(f"bootstrap:{button}@{gs.player.x},{gs.player.y}")
    state["short_term_history"] = history[-20:]
    state["next_node"] = "critic"
    return state


def idle_node(state: AgentState) -> AgentState:
    """Terminal phase state: no further navigation input."""
    gs = GameState.model_validate(state.get("game_state", {}))
    if early_progression.is_satisfied(gs, state):
        action = early_progression.EARLY_PROGRESSION_DONE_ACTION
        reason = "early_progression_satisfied"
    elif starter_quest.is_satisfied(gs, state):
        action = starter_quest.STARTER_QUEST_DONE_ACTION
        reason = "starter_quest_satisfied"
    else:
        action = house_exit.HOUSE_EXIT_DONE_ACTION
        reason = "house_exit_satisfied"
    state["last_action"] = action
    state["last_action_result"] = {"reason": reason, "map_key": gs.map_key}
    state["position_before_action"] = gs.position_key
    state["next_node"] = "critic"
    return state


def planner_node(state: AgentState) -> AgentState:
    """Hierarchical planning: LLM-assisted subgoals with heuristic fallback."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key
    relevant_landmarks = _attach_landmark_context(state, gs)

    objective = EARLY_GAME_OBJECTIVES.get(map_key, "Explore and progress story")
    subgoals = _decompose_subgoals(gs, state)

    llm_result = None
    allows_llm = house_exit.planner_allows_llm(gs, state)
    if state.get("house_exit_complete"):
        allows_llm = allows_llm and starter_quest.planner_allows_llm(gs, state)
    if state.get("starter_quest_complete"):
        allows_llm = allows_llm and early_progression.planner_allows_llm(gs, state)
    if allows_llm:
        llm_result = llm_plan(gs, state, relevant_landmarks)
    if llm_result and llm_result.get("subgoals"):
        subgoals = llm_result["subgoals"]
        state["memory_retrievals"] = [llm_result.get("llm_plan", "")]
    else:
        state["memory_retrievals"] = []

    plan = [
        f"Current area: {gs.player.map_name}",
        objective,
        f"Active subgoal: {state.get('active_subgoal', 'explore')}",
    ]
    state["current_plan"] = plan
    state["subgoals"] = subgoals
    if subgoals:
        replan_count = state.get("replan_count", 0)
        idx = min(replan_count, len(subgoals) - 1)
        state["active_subgoal"] = subgoals[idx]

    state["should_replan"] = False
    state["last_action"] = "plan_replan"
    state["last_action_result"] = {"subgoals": subgoals}
    if generic_is_interact_needed(gs, state):
        state["phase"] = "interact"
        state["next_node"] = "interactor"
        starter_quest.sync_subgoals(gs, state)
        return state
    state["phase"] = "explore"
    state["next_node"] = "navigator"
    return state


def _decompose_subgoals(gs: GameState, state: AgentState | None = None) -> list[str]:
    state = state or {}
    house = house_exit.decompose_subgoals(gs)
    if house:
        return house
    if state.get("house_exit_complete") and not state.get("starter_quest_complete"):
        quest = starter_quest.decompose_subgoals(gs)
        if quest:
            return quest
    if state.get("starter_quest_complete"):
        progress = early_progression.decompose_subgoals(gs)
        if progress:
            return progress
    if gs.battle.in_battle:
        return ["Win battle or run if low HP"]
    return ["Explore current map", "Progress toward next town"]


def _players_house_door_exit(gs: GameState, state: AgentState | None = None) -> str | None:
    state = state or {}
    door: tuple[int, int] | None = None
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN:
        entrance = find_landmark(
            state.get("known_landmarks", []),
            landmark_id=ELMS_LAB_ENTRANCE_ID,
        )
        if entrance is not None and entrance.get("map_key") == gs.map_key:
            door = landmark_coords(entrance)
    lab_exit = starter_quest.door_exit_direction(gs, door=door)
    if lab_exit:
        return lab_exit
    return house_exit.door_exit_direction(gs)


def navigator_node(state: AgentState) -> AgentState:
    """Navigate with pathfinding and LLM direction pick among candidates."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key

    relevant_landmarks = _attach_landmark_context(state, gs)
    target = _navigation_target(gs, map_key=map_key, state=state)
    path = find_path(
        gs.player.x,
        gs.player.y,
        target[0],
        target[1],
        map_key=map_key,
        state=state,
    )
    candidates = _navigation_candidates(gs, target, path, state)
    stuck_count = state.get("stuck_count", 0)
    candidates = expand_candidates_on_stuck(gs, candidates, state, stuck_count=stuck_count)
    candidates = reorder_candidates_visit_aware(gs, candidates, state)

    door_exit = _players_house_door_exit(gs, state)
    llm_choice = llm_navigate(gs, state, candidates, relevant_landmarks, target=target)
    if navigation_arbitration_active(stuck_count, state) and candidates:
        if llm_choice not in candidates:
            llm_choice = candidates[0]
    action = select_navigation_action(
        door_exit=door_exit,
        path=path,
        llm_choice=llm_choice,
        candidates=candidates,
        stuck_count=stuck_count,
        gs=gs,
        state=state,
        target=target,
    )

    history = list(state.get("short_term_history", []))
    history.append(f"navigate:{action}@{gs.player.x},{gs.player.y}")
    state["short_term_history"] = history[-20:]
    state["last_action"] = f"navigate_{action}"
    state["last_action_result"] = {
        "direction": action,
        "target": target,
        "path_length": len(path),
        "candidates": candidates,
    }
    state["position_before_action"] = gs.position_key
    state["facing_before_action"] = gs.player.facing
    state["next_node"] = "critic"
    return state


def _blocked_stairs_up(gs: GameState) -> bool:
    if starter_quest.blocked_lab_exit(gs):
        return True
    return house_exit.blocked_stairs_up(gs)


def _navigation_candidates(
    gs: GameState,
    target: tuple[int, int],
    path: list,
    state: AgentState | None = None,
) -> list[str]:
    """Build direction candidates for pathfinding + LLM selection."""
    state = state or {}
    primary = direction_toward(gs.player.x, gs.player.y, target[0], target[1])
    if primary == "up" and _blocked_stairs_up(gs):
        primary = direction_toward(gs.player.x, gs.player.y, PLAYERS_HOUSE_1F_DOOR[0], PLAYERS_HOUSE_1F_DOOR[1])
    candidates: list[str] = []
    if path:
        for step in path[:3]:
            if step == "up" and _blocked_stairs_up(gs):
                continue
            candidates.append(step)
    if primary != "a" and primary not in candidates:
        candidates.append(primary)
    if house_exit.prefer_interact_candidate(gs) or generic_prefer_interact_candidate(
        gs, state
    ):
        candidates.insert(0, "a")
    elif house_exit.stuck_interact_fallback(gs, state) or generic_stuck_interact_fallback(
        gs, state
    ):
        candidates.append("a")
    if not candidates:
        candidates = _direction_candidates(gs.player.x, gs.player.y, target[0], target[1])
    return list(dict.fromkeys(candidates))


def _direction_candidates(sx: int, sy: int, tx: int, ty: int) -> list[str]:
    primary = direction_toward(sx, sy, tx, ty)
    if primary != "a":
        return [primary]
    return ["right", "up", "down", "left"]


def _navigation_target(
    gs: GameState,
    *,
    map_key: str | None = None,
    state: AgentState | None = None,
) -> tuple[int, int]:
    state = state or {}
    return resolve_navigation_target(gs, state, map_key=map_key or gs.map_key)


def battler_node(state: AgentState) -> AgentState:
    """Battle specialist: LLM decision with HP-heuristic fallback."""
    gs = GameState.model_validate(state.get("game_state", {}))
    battle = gs.battle

    action = llm_battle(gs)
    if action is None:
        if battle.player_active_hp < battle.player_active_max_hp * 0.2 and battle.can_run:
            action = "run"
        else:
            action = "fight"

    state["last_action"] = f"battle_{action}"
    state["last_action_result"] = {"action": action, "phase": battle.phase.value}
    state["next_node"] = "critic"
    return state


def _history_oscillates(history: list[str], *, min_cycles: int = 3) -> bool:
    """Detect navigate*-then-interact cycles at the same tile (stuck-meter evasion)."""
    if len(history) < min_cycles * 2:
        return False
    window = min(len(history), 20)
    entries: list[tuple[str, str]] = []
    for item in history[-window:]:
        if "@" not in item:
            return False
        action, pos = item.split("@", 1)
        entries.append((action.split(":")[0], pos))
    positions = {pos for _, pos in entries}
    if len(positions) != 1:
        return False
    kinds = {kind for kind, _ in entries}
    if kinds != {"navigate", "interact"}:
        return False
    cycles = 0
    idx = 0
    while idx < len(entries):
        nav_count = 0
        while idx < len(entries) and entries[idx][0] == "navigate":
            nav_count += 1
            idx += 1
        interact_count = 0
        while idx < len(entries) and entries[idx][0] == "interact":
            interact_count += 1
            idx += 1
        if nav_count > 0 and interact_count > 0:
            cycles += 1
        elif nav_count > 0:
            break
    return cycles >= min_cycles


def _history_interact_repeats(history: list[str], *, min_count: int = 5) -> bool:
    """Detect same-tile interact spam with no navigation progress."""
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


def critic_node(state: AgentState) -> AgentState:
    """Post-action review: loop detection and risk veto. Always routes through memory."""
    gs = GameState.model_validate(state.get("game_state", {}))
    history = state.get("short_term_history", [])
    stuck = state.get("stuck_count", 0)

    recent = history[-5:] if history else []
    dialog_active = generic_is_interact_needed(gs, state)
    repetition = (
        not dialog_active
        and len(recent) >= 3
        and len(set(recent[-3:])) == 1
        and stuck >= 2
    )
    oscillation = not dialog_active and _history_oscillates(history, min_cycles=3)
    interact_spam = (
        not dialog_active
        and stuck >= 2
        and _history_interact_repeats(history, min_count=5)
    )

    if repetition or oscillation or interact_spam or stuck >= STUCK_THRESHOLD:
        state["critic_verdict"] = "replan"
        state["critic_notes"] = "Detected loop or high stuck count"
        state["should_replan"] = True
        state["replan_count"] = state.get("replan_count", 0) + 1
        events = list(state.get("replan_events", []))
        events.append(
            {
                "step": state.get("metrics", {}).get("steps", 0),
                "stuck_count": stuck,
                "position": gs.position_key,
                "recovered": False,
            }
        )
        state["replan_events"] = events[-50:]
        _capture_stuck_episode(state, gs)
    elif state.get("last_action", "").startswith("battle_run"):
        state["critic_verdict"] = "caution"
        state["critic_notes"] = "Retreated from battle"
    else:
        state["critic_verdict"] = "proceed"
        state["critic_notes"] = "Action acceptable"

    state["next_node"] = "memory"
    return state


def memory_node(state: AgentState) -> AgentState:
    """Memory manager: milestones, step counter, map tracking."""
    gs = GameState.model_validate(state.get("game_state", {}))
    milestones = list(state.get("milestones", []))
    maps_visited = list(state.get("maps_visited", []))

    discoveries: list[dict[str, Any]] = []
    if gs.map_key not in maps_visited:
        maps_visited.append(gs.map_key)
        discoveries.append(discover_map_visit_landmark(gs))
        if (
            gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE
            and not landmark_known(state.get("known_landmarks", []), MR_POKEMONS_HOUSE_ENTRANCE_ID)
        ):
            discoveries.append(discover_mr_pokemon_entrance_landmark(gs))
    state["maps_visited"] = maps_visited

    transition = state.get("last_map_transition") or {}
    if transition.get("to_map"):
        from_map = transition.get("from_map")
        to_map = transition.get("to_map")
        from_pos = transition.get("from_pos") or {}
        known = list(state.get("known_landmarks", [])) + discoveries
        if (
            to_map == MAP_KEY_ELMS_LAB
            and not landmark_known(known, ELMS_LAB_INTERIOR_ID)
        ):
            discoveries.extend(
                discover_elms_lab_landmarks(
                    gs,
                    entrance_map_key=from_pos.get("map_key"),
                    entrance_x=from_pos.get("x"),
                    entrance_y=from_pos.get("y"),
                )
            )
        for landmark in discover_quest_transition_landmarks(
            from_map=from_map,
            to_map=to_map,
            from_pos=from_pos,
        ):
            if not landmark_known(known, str(landmark.get("id"))):
                discoveries.append(landmark)
                known.append(landmark)
        state["last_map_transition"] = {}

    milestone = _check_milestone(gs, state, maps_visited)
    if milestone and milestone not in milestones:
        milestones.append(milestone)
        logger.info("Milestone: %s", milestone)
        if milestone == house_exit.HOUSE_EXIT_MILESTONE:
            house_exit.on_house_exit_complete(state, gs)
        elif milestone == starter_quest.MILESTONE_RIVAL_BATTLE:
            starter_quest.on_starter_quest_complete(state, gs)
        elif milestone == early_progression.MILESTONE_REACHED_CHERRYGROVE:
            early_progression.on_early_progression_complete(state, gs)

    if milestone == starter_quest.MILESTONE_ENTERED_LAB and not landmark_known(
        state.get("known_landmarks", []), ELMS_LAB_INTERIOR_ID
    ):
        discoveries.extend(discover_elms_lab_landmarks(gs))

    if discoveries:
        _persist_landmark_discoveries(state, discoveries)

    starter_quest.ensure_house_exit_complete(gs, state)
    if starter_quest.in_starter_quest(gs, state) or gs.map_key == MAP_KEY_ELMS_LAB:
        starter_quest.sync_subgoals(gs, state)
    elif early_progression.in_early_progression(gs, state):
        early_progression.sync_subgoals(gs, state)

    state["milestones"] = milestones
    state["badges_at_last_check"] = gs.total_badges
    metrics = dict(state.get("metrics", {}))
    metrics["steps"] = metrics.get("steps", 0) + 1
    state["metrics"] = metrics
    state["next_node"] = "supervisor"
    return state


def _check_milestone(
    gs: GameState, state: AgentState, maps_visited: list[str]
) -> str | None:
    earned = state.get("milestones", [])
    house = house_exit.house_milestone(gs, maps_visited)
    if house and house not in earned:
        return house
    quest = starter_quest.starter_milestone(gs, maps_visited)
    if quest and quest not in earned:
        return quest
    if gs.map_key == MAP_KEY_ROUTE_29 and maps_visited.count(MAP_KEY_ROUTE_29) == 1:
        return "Reached Route 29"
    if gs.map_key == early_progression.MAP_KEY_CHERRYGROVE_CITY and maps_visited.count(
        early_progression.MAP_KEY_CHERRYGROVE_CITY
    ) == 1:
        return early_progression.MILESTONE_REACHED_CHERRYGROVE
    if gs.map_key == "1:4" and maps_visited.count("1:4") == 1:
        return "Reached Violet City"
    if gs.battle.in_battle and gs.battle.phase.value == "wild":
        wild_key = "wild_encounter"
        if wild_key not in state.get("milestones", []):
            return "Wild Pokemon encounter"
    badges = gs.total_badges
    if badges > state.get("badges_at_last_check", 0):
        return f"Earned badge (total: {badges})"
    return None


def apply_action_node(state: AgentState, emulator: Any = None) -> AgentState:
    """Execute last_action against emulator and update stuck meter from movement."""
    from src.tools import pokemon_tools

    action = state.get("last_action", "")
    if not action:
        return state

    pos_before = state.get("position_before_action", "")
    if emulator is None:
        if action.startswith("navigate_") and pos_before:
            _update_stuck_from_movement(state, action, pos_before, pos_before)
        return state
    if not pos_before:
        gs_before = GameState.model_validate(state.get("game_state", {}))
        pos_before = gs_before.position_key

    gs_before = GameState.model_validate(state.get("game_state", {}))
    map_before = gs_before.map_key

    pokemon_tools.bind_emulator(emulator)
    try:
        if action == "wait_script":
            emulator.tick(SCRIPT_WAIT_TICKS)
        elif action == "plan_replan":
            emulator.tick(1)
        elif action in (
            house_exit.HOUSE_EXIT_DONE_ACTION,
            starter_quest.STARTER_QUEST_DONE_ACTION,
            early_progression.EARLY_PROGRESSION_DONE_ACTION,
        ):
            emulator.tick(1)
        elif (
            action.startswith("navigate_")
            or action.startswith("bootstrap_")
            or action.startswith("interact_")
        ):
            direction = action.split("_", 1)[1]
            if direction in ("up", "down", "left", "right", "a", "b", "start", "select"):
                hold = 12 if direction in ("up", "down", "left", "right") else 8
                if action.startswith("interact_") and direction == "a":
                    hold = INTERACT_HOLD_FRAMES
                emulator.press_button(direction, hold_frames=hold)  # type: ignore[arg-type]
                if direction in ("up", "down", "left", "right"):
                    emulator.tick(30)
                elif action.startswith("interact_"):
                    emulator.tick(45)
        elif action.startswith("battle_"):
            battle_action = action.replace("battle_", "")
            pokemon_tools.battle_decide.invoke({"action": battle_action})
        gs = emulator.get_game_state()
        state = update_game_state(state, gs)
        if not state.get("bootstrap_complete") and (gs.raw_metadata or {}).get(
            "movement_ready"
        ):
            state["bootstrap_complete"] = True
            state["phase"] = "explore"
            state["stuck_count"] = 0
        if map_before != gs.map_key:
            parsed = parse_position_key(pos_before)
            if parsed is not None:
                from_map, from_x, from_y = parsed
                state["last_map_transition"] = {
                    "from_map": from_map,
                    "from_pos": {"map_key": from_map, "x": from_x, "y": from_y},
                    "to_map": gs.map_key,
                    "to_pos": {"x": gs.player.x, "y": gs.player.y},
                }
        house_exit.on_map_change(map_before, gs, state, action=action)
        starter_quest.on_map_change(map_before, gs, state, action=action)
        if action.startswith("bootstrap_"):
            from src.emulator.bootstrap import (
                BootstrapResult,
                apply_bootstrap_metadata,
                is_bootstrap_done,
            )

            if pos_before and gs.position_key != pos_before:
                state["movement_observed"] = True
            if is_bootstrap_done(emulator, gs, state):
                gs = apply_bootstrap_metadata(
                    gs,
                    BootstrapResult(
                        success=True,
                        movement_ready=True,
                        map_loaded=True,
                        actions_taken=state.get("bootstrap_action_index", 0),
                        frames_elapsed=0,
                    ),
                )
                state = update_game_state(state, gs)
                state["bootstrap_complete"] = True
                state["phase"] = "explore"
                state["stuck_count"] = 0
            else:
                state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        elif action.startswith("interact_"):
            _update_stuck_from_interaction(state, action, pos_before, gs)
            if (
                gs.map_key == MAP_KEY_ELMS_LAB
                and (gs.player.x, gs.player.y) in ((4, 2), (5, 2), (4, 3))
                and (gs.in_text_box or bool((gs.raw_metadata or {}).get("in_script")))
            ):
                state["lab_desk_dialog_done"] = True
        else:
            _update_stuck_from_movement(
                state,
                action,
                pos_before,
                gs.position_key,
                gs,
            )
    except Exception as exc:
        state["error"] = str(exc)
        logger.error("Action execution failed: %s", exc)

    return state


def _update_stuck_from_movement(
    state: AgentState,
    action: str,
    pos_before: str,
    pos_after: str,
    gs: GameState | None = None,
) -> None:
    """Increment stuck only when a navigation action fails to change position."""
    if not action.startswith("navigate_"):
        return
    if action.endswith("_a"):
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        return
    moved = pos_before != pos_after
    if moved:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
        if gs is not None:
            parsed = parse_position_key(pos_after)
            if parsed is not None:
                _, x, y = parsed
                record_session_walkable(state, gs.map_key, x, y)
            _mark_replan_recovery(state, gs, pos_before, pos_after)
        return
    state["stuck_count"] = state.get("stuck_count", 0) + 1


def _mark_replan_recovery(
    state: AgentState,
    gs: GameState,
    pos_before: str,
    pos_after: str,
) -> None:
    events = list(state.get("replan_events", []))
    if not events or events[-1].get("recovered"):
        return
    last = events[-1]
    if pos_before != pos_after or state.get("stuck_count", 0) < last.get("stuck_count", 0):
        last = {**last, "recovered": True}
        events[-1] = last
        state["replan_events"] = events


def _update_stuck_from_interaction(
    state: AgentState,
    action: str,
    pos_before: str,
    gs: GameState,
) -> None:
    """Dialog interactions advance story without map movement."""
    del action
    meta = gs.raw_metadata or {}
    if house_exit.mom_scene_pending(gs):
        state["stuck_count"] = 0
        state["phase"] = "explore"
        return
    if pos_before != gs.position_key:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 2)
        _mark_replan_recovery(state, gs, pos_before, gs.position_key)
    elif gs.in_text_box or bool(meta.get("in_script")):
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
    else:
        state["stuck_count"] = state.get("stuck_count", 0) + 1