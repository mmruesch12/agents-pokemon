"""Custom evaluators: progress, stuck frequency, coherence."""

from __future__ import annotations

from typing import Any

from src.graph.state import AgentState


def progress_per_steps(state: AgentState, *, window: int = 500) -> float:
    """Measure progress: unique positions visited per step."""
    steps = max(1, state.get("metrics", {}).get("steps", 1))
    visited = len(set(state.get("visited_positions", [])))
    return visited / min(steps, window)


def stuck_frequency(state: AgentState) -> float:
    """Ratio of stuck count to steps."""
    steps = max(1, state.get("metrics", {}).get("steps", 1))
    stuck = state.get("stuck_count", 0)
    return stuck / steps


def coherence_score(state: AgentState) -> float:
    """Score plan/action coherence: subgoal alignment with last action."""
    subgoal = state.get("active_subgoal", "").lower()
    action = state.get("last_action", "").lower()
    plan = " ".join(state.get("current_plan", [])).lower()

    score = 0.5
    if subgoal and any(word in action or word in plan for word in subgoal.split()[:2]):
        score += 0.25
    if state.get("critic_verdict") == "proceed":
        score += 0.25
    if state.get("critic_verdict") == "replan":
        score -= 0.2
    return max(0.0, min(1.0, score))


def battle_efficiency(state: AgentState) -> float:
    """Simple battle efficiency metric."""
    metrics = state.get("metrics", {})
    battles = metrics.get("battles_won", 0) + metrics.get("battles_lost", 0)
    if battles == 0:
        return 1.0
    return metrics.get("battles_won", 0) / battles


def exploration_coverage(state: AgentState) -> float:
    """Fraction of map positions explored (approximate)."""
    visited = len(set(state.get("visited_positions", [])))
    return min(1.0, visited / 20.0)


def evaluate_run(state: AgentState) -> dict[str, float]:
    """Run all evaluators and return metrics dict."""
    return {
        "progress_per_steps": progress_per_steps(state),
        "stuck_frequency": stuck_frequency(state),
        "coherence": coherence_score(state),
        "battle_efficiency": battle_efficiency(state),
        "exploration_coverage": exploration_coverage(state),
    }


def evaluate_against_dataset(
    state: AgentState, dataset_entry: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate state against a dataset entry."""
    gs = state.get("game_state", {})
    inp = dataset_entry.get("input", {})
    matches = all(
        gs.get(k) == v or gs.get("player", {}).get(k) == v
        for k, v in inp.items()
        if k not in ("in_battle", "battle_mode")
    )
    return {
        "entry_id": dataset_entry["id"],
        "input_match": matches,
        "scores": evaluate_run(state),
        "milestones": state.get("milestones", []),
    }