"""Multi-agent graph nodes: Supervisor, Planner, Navigator, Battler, Critic, Memory."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.emulator.bootstrap import needs_bootstrap, pick_bootstrap_button
from src.graph.llm import llm_battle, llm_navigate, llm_plan
from src.graph.pathfinding import direction_toward, find_path
from src.graph.state import AgentState, update_game_state
from src.state.models import GameState

logger = logging.getLogger(__name__)

STUCK_THRESHOLD = int(os.getenv("STUCK_THRESHOLD", "10"))
EARLY_GAME_OBJECTIVES = {
    "3:4": "Leave bedroom, talk to Mom on 1F, then head to Professor Elm",
    "0:0": "Explore New Bark Town and head east toward Route 29",
    "1:1": "Travel north through Route 29 toward Cherrygrove City",
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


def bootstrap_node(state: AgentState) -> AgentState:
    """Press through title screens, dialogs, name entry, and clock setup."""
    gs = GameState.model_validate(state.get("game_state", {}))
    idx = state.get("bootstrap_action_index", 0)
    loaded_map = state.get("loaded_map_key")
    if isinstance(loaded_map, list):
        loaded_map = tuple(loaded_map)
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


def planner_node(state: AgentState) -> AgentState:
    """Hierarchical planning: LLM-assisted subgoals with heuristic fallback."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key

    objective = EARLY_GAME_OBJECTIVES.get(map_key, "Explore and progress story")
    subgoals = _decompose_subgoals(gs)

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


def _decompose_subgoals(gs: GameState) -> list[str]:
    if gs.map_key == "3:4":
        return ["Leave bedroom via stairs", "Talk to Mom downstairs", "Go to Professor Elm"]
    if gs.map_key == "0:0":
        if gs.player.x < 10:
            return ["Move east in New Bark Town", "Exit toward Route 29"]
        return ["Exit New Bark Town east", "Enter Route 29"]
    if gs.map_key == "1:1":
        return ["Travel north on Route 29", "Reach Cherrygrove City"]
    if gs.battle.in_battle:
        return ["Win battle or run if low HP"]
    return ["Explore current map", "Progress toward next town"]


def _effective_map_key(gs: GameState, state: AgentState) -> str:
    """Prefer loaded_map_key when reader still reports 0:0 after bootstrap."""
    if gs.map_key != "0:0" or gs.party_count > 0:
        return gs.map_key
    loaded = state.get("loaded_map_key")
    if isinstance(loaded, (list, tuple)) and len(loaded) == 2:
        return f"{loaded[0]}:{loaded[1]}"
    return gs.map_key


def navigator_node(state: AgentState) -> AgentState:
    """Navigate with pathfinding and LLM direction pick among candidates."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = _effective_map_key(gs, state)

    target = _navigation_target(gs, map_key=map_key)
    path = find_path(gs.player.x, gs.player.y, target[0], target[1], map_key=map_key)
    candidates = _navigation_candidates(gs, target, path)

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


def _navigation_candidates(
    gs: GameState, target: tuple[int, int], path: list
) -> list[str]:
    """Build direction candidates for pathfinding + LLM selection."""
    primary = direction_toward(gs.player.x, gs.player.y, target[0], target[1])
    candidates: list[str] = []
    if path:
        candidates.extend(path[:3])
    if primary != "a" and primary not in candidates:
        candidates.append(primary)
    if not candidates:
        candidates = _direction_candidates(gs.player.x, gs.player.y, target[0], target[1])
    return list(dict.fromkeys(candidates))


def _direction_candidates(sx: int, sy: int, tx: int, ty: int) -> list[str]:
    primary = direction_toward(sx, sy, tx, ty)
    if primary != "a":
        return [primary]
    return ["right", "up", "down", "left"]


def _navigation_target(gs: GameState, *, map_key: str | None = None) -> tuple[int, int]:
    map_key = map_key or gs.map_key
    if map_key == "3:4":
        return (gs.player.x, gs.player.y + 2)
    if map_key == "0:0":
        return (gs.player.x + 2, gs.player.y)
    if map_key == "1:1":
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
    if gs.map_key == "1:1" and maps_visited.count("1:1") == 1:
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

    pokemon_tools.bind_emulator(emulator)
    try:
        from src.emulator.bootstrap import MOVEMENT_PROBE_ADDR, read_memory_byte

        probe_before = None
        if action.startswith(("navigate_", "bootstrap_")):
            probe_before = read_memory_byte(emulator, MOVEMENT_PROBE_ADDR)

        if action.startswith("navigate_") or action.startswith("bootstrap_"):
            direction = action.split("_", 1)[1]
            if direction in ("up", "down", "left", "right", "a", "b", "start", "select"):
                hold = 12 if direction in ("up", "down", "left", "right") else 8
                emulator.press_button(direction, hold_frames=hold)  # type: ignore[arg-type]
                if direction in ("up", "down", "left", "right"):
                    emulator.tick(30)
        elif action.startswith("battle_"):
            battle_action = action.replace("battle_", "")
            pokemon_tools.battle_decide.invoke({"action": battle_action})
        gs = emulator.get_game_state()
        state = update_game_state(state, gs)
        if action.startswith("bootstrap_"):
            from src.emulator.bootstrap import (
                BootstrapResult,
                apply_bootstrap_metadata,
                is_bootstrap_done,
                read_loaded_map,
            )

            loaded_map = read_loaded_map(emulator)
            state["loaded_map_key"] = loaded_map
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
        else:
            probe_after = (
                read_memory_byte(emulator, MOVEMENT_PROBE_ADDR)
                if probe_before is not None
                else None
            )
            _update_stuck_from_movement(
                state,
                action,
                pos_before,
                gs.position_key,
                probe_before=probe_before,
                probe_after=probe_after,
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
    *,
    probe_before: int | None = None,
    probe_after: int | None = None,
) -> None:
    """Increment stuck only when a navigation action fails to change position."""
    if not action.startswith("navigate_"):
        return
    moved = pos_before != pos_after
    if moved:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)
    else:
        state["stuck_count"] = state.get("stuck_count", 0) + 1