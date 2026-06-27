"""Multi-agent graph nodes: Supervisor, Planner, Navigator, Battler, Critic, Memory."""

from __future__ import annotations

import logging
from typing import Any

from src.graph.pathfinding import find_path
from src.graph.state import AgentState, update_game_state
from src.state.models import GameState

logger = logging.getLogger(__name__)

STUCK_THRESHOLD = 10
EARLY_GAME_OBJECTIVES = {
    "0:0": "Explore New Bark Town and head east toward Route 29",
    "1:1": "Travel north through Route 29 toward Cherrygrove City",
    "1:2": "Visit Pokemon Center and continue toward Violet City",
    "1:4": "Challenge Violet City gym (first badge goal)",
}


def supervisor_node(state: AgentState) -> AgentState:
    """Route to appropriate specialist based on game phase."""
    gs = GameState.model_validate(state.get("game_state", {}))
    phase = state.get("phase", "explore")

    if gs.battle.in_battle:
        state["next_node"] = "battler"
        state["phase"] = "battle"
    elif state.get("should_replan"):
        state["next_node"] = "planner"
    elif state.get("stuck_count", 0) >= STUCK_THRESHOLD:
        state["next_node"] = "critic"
    elif phase == "plan":
        state["next_node"] = "planner"
    else:
        state["next_node"] = "navigator"

    logger.debug("Supervisor routing to %s", state["next_node"])
    return state


def planner_node(state: AgentState) -> AgentState:
    """Hierarchical planning: decompose goals into subgoals."""
    gs = GameState.model_validate(state.get("game_state", {}))
    map_key = gs.map_key

    objective = EARLY_GAME_OBJECTIVES.get(map_key, "Explore and progress story")
    plan = [
        f"Current area: {gs.player.map_name}",
        objective,
        f"Active subgoal: {state.get('active_subgoal', 'explore')}",
    ]

    subgoals = _decompose_subgoals(gs)
    state["current_plan"] = plan
    state["subgoals"] = subgoals
    if subgoals:
        state["active_subgoal"] = subgoals[0]
    state["should_replan"] = False
    state["phase"] = "explore"
    state["next_node"] = "navigator"
    return state


def _decompose_subgoals(gs: GameState) -> list[str]:
    if gs.map_key == "0:0":
        if gs.player.x < 10:
            return ["Move east in New Bark Town", "Exit toward Route 29"]
        return ["Exit New Bark Town east", "Enter Route 29"]
    if gs.map_key == "1:1":
        return ["Travel north on Route 29", "Reach Cherrygrove City"]
    if gs.battle.in_battle:
        return ["Win battle or run if low HP"]
    return ["Explore current map", "Progress toward next town"]


def navigator_node(state: AgentState) -> AgentState:
    """Navigate with visited memory and pathfinding."""
    gs = GameState.model_validate(state.get("game_state", {}))
    visited = set(state.get("visited_positions", []))

    target = _navigation_target(gs)
    path = find_path(gs.player.x, gs.player.y, target[0], target[1], map_key=gs.map_key)
    action = path[0] if path else "a"

    history = list(state.get("short_term_history", []))
    history.append(f"navigate:{action} toward {target}")
    state["short_term_history"] = history[-20:]
    state["last_action"] = f"navigate_{action}"
    state["last_action_result"] = {
        "direction": action,
        "target": target,
        "path_length": len(path),
    }
    state["next_node"] = "critic"

    if gs.position_key in visited:
        state["stuck_count"] = state.get("stuck_count", 0) + 1
    else:
        state["stuck_count"] = max(0, state.get("stuck_count", 0) - 1)

    return state


def _navigation_target(gs: GameState) -> tuple[int, int]:
    if gs.map_key == "0:0":
        return (gs.player.x + 2, gs.player.y)
    if gs.map_key == "1:1":
        return (gs.player.x, gs.player.y - 2)
    return (gs.player.x + 1, gs.player.y)


def battler_node(state: AgentState) -> AgentState:
    """Battle specialist: decide fight/run based on HP."""
    gs = GameState.model_validate(state.get("game_state", {}))
    battle = gs.battle

    if battle.player_active_hp < battle.player_active_max_hp * 0.2 and battle.can_run:
        action = "run"
    elif battle.enemy_hp < battle.enemy_max_hp * 0.3:
        action = "fight"
    else:
        action = "fight"

    state["last_action"] = f"battle_{action}"
    state["last_action_result"] = {"action": action, "phase": battle.phase.value}
    state["next_node"] = "critic"
    return state


def critic_node(state: AgentState) -> AgentState:
    """Post-action review: loop detection and risk veto."""
    history = state.get("short_term_history", [])
    stuck = state.get("stuck_count", 0)

    recent = history[-5:] if history else []
    repetition = len(recent) >= 3 and len(set(recent[-3:])) == 1

    if repetition or stuck >= STUCK_THRESHOLD:
        state["critic_verdict"] = "replan"
        state["critic_notes"] = "Detected loop or high stuck count"
        state["should_replan"] = True
        state["next_node"] = "planner"
    elif state.get("last_action", "").startswith("battle_run"):
        state["critic_verdict"] = "caution"
        state["critic_notes"] = "Retreated from battle"
        state["next_node"] = "memory"
    else:
        state["critic_verdict"] = "proceed"
        state["critic_notes"] = "Action acceptable"
        state["next_node"] = "memory"

    return state


def memory_node(state: AgentState) -> AgentState:
    """Memory manager: update short-term history and milestone tracking."""
    gs = GameState.model_validate(state.get("game_state", {}))
    milestones = list(state.get("milestones", []))

    milestone = _check_milestone(gs, state)
    if milestone and milestone not in milestones:
        milestones.append(milestone)
        logger.info("Milestone: %s", milestone)

    state["milestones"] = milestones
    metrics = dict(state.get("metrics", {}))
    metrics["steps"] = metrics.get("steps", 0) + 1
    state["metrics"] = metrics
    state["next_node"] = "supervisor"
    return state


def _check_milestone(gs: GameState, state: AgentState) -> str | None:
    visited = state.get("visited_positions", [])
    if gs.map_key == "1:1" and gs.map_key not in [v.split(":")[0] + ":" + v.split(":")[1] for v in visited[:1]]:
        return "Reached Route 29"
    if gs.map_key == "1:2":
        return "Reached Cherrygrove City"
    if gs.map_key == "1:4":
        return "Reached Violet City"
    if gs.battle.in_battle and gs.battle.phase.value == "wild":
        return "Wild Pokemon encounter"
    if gs.total_badges > state.get("metrics", {}).get("badges_earned", 0):
        return f"Earned badge (total: {gs.total_badges})"
    return None


def apply_action_node(state: AgentState, emulator: Any = None) -> AgentState:
    """Execute last_action against emulator if bound."""
    from src.tools import pokemon_tools

    action = state.get("last_action", "")
    if not action or emulator is None:
        return state

    pokemon_tools.bind_emulator(emulator)
    try:
        if action.startswith("navigate_"):
            direction = action.replace("navigate_", "")
            pokemon_tools.press_button.invoke({"button": direction})
        elif action.startswith("battle_"):
            battle_action = action.replace("battle_", "")
            pokemon_tools.battle_decide.invoke({"action": battle_action})
        gs = emulator.get_game_state()
        state = update_game_state(state, gs)
    except Exception as exc:
        state["error"] = str(exc)
        logger.error("Action execution failed: %s", exc)

    return state