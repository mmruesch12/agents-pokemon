"""Multi-agent graph nodes: Supervisor, Planner, Navigator, Battler, Critic, Memory."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.emulator.bootstrap import needs_bootstrap, pick_bootstrap_button
from src.graph.llm import llm_battle, llm_navigate, llm_plan
from src.graph.pathfinding import direction_toward, find_path
from src.graph.phases import house_exit
from src.graph.state import AgentState, update_game_state
from src.state.gold_state_reader import (
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    MAP_KEY_ROUTE_29,
    PLAYERS_HOUSE_1F_DOOR,
)
from src.state.models import GameState
from src.state.script_constants import (
    MOM_SCENE_ENTRY_POS,
    SCRIPT_FLAG_SCRIPT_RUNNING,
    SCRIPT_READ,
    SCRIPT_WAIT,
    SCRIPT_WAIT_MOVEMENT,
    joypad_input_blocked,
)

logger = logging.getLogger(__name__)

STUCK_THRESHOLD = int(os.getenv("STUCK_THRESHOLD", "10"))
INTERACT_HOLD_FRAMES = int(os.getenv("INTERACT_HOLD_FRAMES", "30"))
SCRIPT_WAIT_TICKS = int(os.getenv("SCRIPT_WAIT_TICKS", "45"))
EARLY_GAME_OBJECTIVES = {
    MAP_KEY_PLAYERS_HOUSE_2F: "Leave bedroom via stairs, talk to Mom on 1F, then head to Professor Elm",
    MAP_KEY_PLAYERS_HOUSE_1F: "Talk to Mom and leave through the front door to New Bark Town",
    MAP_KEY_NEW_BARK_TOWN: "Explore New Bark Town and head east toward Route 29",
    MAP_KEY_ROUTE_29: "Travel north through Route 29 toward Cherrygrove City",
    "1:2": "Visit Pokemon Center and continue toward Violet City",
    "1:4": "Challenge Violet City gym (first badge goal)",
}


def supervisor_node(state: AgentState) -> AgentState:
    """Route to appropriate specialist based on game phase."""
    gs = GameState.model_validate(state.get("game_state", {}))

    if gs.battle.in_battle:
        state["next_node"] = "battler"
        state["phase"] = "battle"
    elif needs_bootstrap(gs, state):
        state["next_node"] = "bootstrap"
        state["phase"] = "bootstrap"
    elif house_exit.is_satisfied(gs, state):
        state["next_node"] = "idle"
        state["phase"] = "house_exit_done"
    elif needs_script_wait(gs, state):
        state["next_node"] = "waiter"
        state["phase"] = "wait"
    elif needs_interaction(gs, state):
        state["next_node"] = "interactor"
        state["phase"] = "interact"
    elif house_exit.force_interactor(gs, state):
        state["next_node"] = "interactor"
        state["phase"] = "interact"
    elif state.get("should_replan"):
        state["next_node"] = "planner"
    elif state.get("stuck_count", 0) >= STUCK_THRESHOLD:
        state["next_node"] = "planner"
        state["should_replan"] = True
    elif state.get("phase") == "plan":
        state["next_node"] = "planner"
    else:
        state["next_node"] = "navigator"

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
    """True when the game expects A/B dialog input instead of movement."""
    state = state or {}
    if gs.battle.in_battle or needs_bootstrap(gs, state) or needs_script_wait(gs, state):
        return False
    meta = gs.raw_metadata or {}
    joypad_disable = meta.get("joypad_disable", 0)
    blocked = joypad_input_blocked(joypad_disable)
    if meta.get("script_mode") == SCRIPT_READ and not blocked:
        return True
    if gs.in_text_box and not blocked:
        return True
    return house_exit.needs_house_interaction(gs, state)


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
    state["next_node"] = "critic"
    return state


def interactor_node(state: AgentState) -> AgentState:
    """Advance dialog and scripted indoor scenes with A/B."""
    gs = GameState.model_validate(state.get("game_state", {}))
    idx = state.get("interact_action_index", 0)
    button = "a" if idx % 8 != 7 else "b"
    state["interact_action_index"] = idx + 1
    state["last_action"] = f"interact_{button}"
    state["last_action_result"] = {"button": button, "interact_index": idx}
    state["position_before_action"] = gs.position_key
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
    """Terminal house-exit state: no further navigation input."""
    gs = GameState.model_validate(state.get("game_state", {}))
    state["last_action"] = house_exit.HOUSE_EXIT_DONE_ACTION
    state["last_action_result"] = {"reason": "house_exit_satisfied", "map_key": gs.map_key}
    state["position_before_action"] = gs.position_key
    state["next_node"] = "critic"
    return state


def planner_node(state: AgentState) -> AgentState:
    """Hierarchical planning: LLM-assisted subgoals with heuristic fallback."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key

    objective = EARLY_GAME_OBJECTIVES.get(map_key, "Explore and progress story")
    subgoals = _decompose_subgoals(gs, state)

    llm_result = None
    if house_exit.planner_allows_llm(gs, state):
        llm_result = llm_plan(gs, state)
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
    state["phase"] = "explore"
    state["next_node"] = "navigator"
    return state


def _decompose_subgoals(gs: GameState, state: AgentState | None = None) -> list[str]:
    state = state or {}
    house = house_exit.decompose_subgoals(gs)
    if house:
        return house
    if gs.map_key == "24:3":
        return ["Travel north on Route 29", "Reach Cherrygrove City"]
    if gs.battle.in_battle:
        return ["Win battle or run if low HP"]
    return ["Explore current map", "Progress toward next town"]


def _players_house_door_exit(gs: GameState) -> str | None:
    return house_exit.door_exit_direction(gs)


def navigator_node(state: AgentState) -> AgentState:
    """Navigate with pathfinding and LLM direction pick among candidates."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key

    target = _navigation_target(gs, map_key=map_key, state=state)
    path = find_path(gs.player.x, gs.player.y, target[0], target[1], map_key=map_key)
    candidates = _navigation_candidates(gs, target, path, state)

    door_exit = _players_house_door_exit(gs)
    if door_exit:
        action = door_exit
    else:
        llm_choice = llm_navigate(gs, state, candidates)
        if llm_choice and llm_choice in candidates:
            action = llm_choice
        elif path:
            action = path[0]
        else:
            action = direction_toward(gs.player.x, gs.player.y, target[0], target[1])

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
    state["next_node"] = "critic"
    return state


def _blocked_stairs_up(gs: GameState) -> bool:
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
    if house_exit.prefer_interact_candidate(gs):
        candidates.insert(0, "a")
    elif house_exit.stuck_interact_fallback(gs, state):
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
    map_key = map_key or gs.map_key
    phase_target = house_exit.navigation_target(gs, map_key=map_key, state=state)
    if phase_target is not None:
        return phase_target
    if map_key == "24:3":
        return (gs.player.x, gs.player.y - 2)
    return (gs.player.x + 1, gs.player.y)


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


def critic_node(state: AgentState) -> AgentState:
    """Post-action review: loop detection and risk veto. Always routes through memory."""
    history = state.get("short_term_history", [])
    stuck = state.get("stuck_count", 0)

    recent = history[-5:] if history else []
    repetition = len(recent) >= 3 and len(set(recent[-3:])) == 1 and stuck >= 3

    gs = GameState.model_validate(state.get("game_state", {}))
    if repetition or stuck >= STUCK_THRESHOLD:
        state["critic_verdict"] = "replan"
        state["critic_notes"] = "Detected loop or high stuck count"
        state["should_replan"] = True
        state["replan_count"] = state.get("replan_count", 0) + 1
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

    if gs.map_key not in maps_visited:
        maps_visited.append(gs.map_key)
    state["maps_visited"] = maps_visited

    milestone = _check_milestone(gs, state, maps_visited)
    if milestone and milestone not in milestones:
        milestones.append(milestone)
        logger.info("Milestone: %s", milestone)
        if milestone == house_exit.HOUSE_EXIT_MILESTONE:
            house_exit.on_house_exit_complete(state, gs)

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
    house = house_exit.house_milestone(gs, maps_visited)
    if house:
        return house
    if gs.map_key == MAP_KEY_ROUTE_29 and maps_visited.count(MAP_KEY_ROUTE_29) == 1:
        return "Reached Route 29"
    if gs.map_key == "1:2" and maps_visited.count("1:2") == 1:
        return "Reached Cherrygrove City"
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
        elif action == house_exit.HOUSE_EXIT_DONE_ACTION:
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
        house_exit.on_map_change(map_before, gs, state, action=action)
        if action.startswith("bootstrap_"):
            from src.emulator.bootstrap import (
                BootstrapResult,
                apply_bootstrap_metadata,
                is_bootstrap_done,
                read_loaded_map,
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
        else:
            _update_stuck_from_movement(
                state,
                action,
                pos_before,
                gs.position_key,
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
    else:
        state["stuck_count"] = state.get("stuck_count", 0) + 1


def _update_stuck_from_interaction(
    state: AgentState,
    action: str,
    pos_before: str,
    gs: GameState,
) -> None:
    """Dialog interactions advance story without map movement."""
    del action
    meta = gs.raw_metadata or {}
    if meta.get("mom_scene_complete"):
        state["stuck_count"] = 0
        state["phase"] = "explore"
        return
    if pos_before != gs.position_key:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 2)
    else:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)