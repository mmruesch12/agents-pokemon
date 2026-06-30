"""Custom evaluators: progress, stuck frequency, coherence, Phase-4 gates."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from src.graph.state import AgentState

_COORD_TUPLE_RE = re.compile(r"\(\s*\d+\s*,\s*\d+\s*\)")


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


def milestone_completion(state: AgentState) -> float:
    """Fraction of early-game milestones earned (dataset-aligned)."""
    milestones = state.get("milestones", [])
    expected = 6
    return min(1.0, len(milestones) / expected)


def stuck_events_per_milestone(state: AgentState) -> float:
    """Critic replans per milestone — self-correction load."""
    replans = state.get("replan_count", 0)
    milestones = max(1, len(state.get("milestones", [])))
    return replans / milestones


def replan_recovery_rate(state: AgentState) -> float:
    """Share of replans followed by position change or stuck reduction."""
    events = state.get("replan_events", [])
    if not events:
        return 1.0 if state.get("replan_count", 0) == 0 else 0.0
    recovered = sum(1 for event in events if event.get("recovered"))
    return recovered / len(events)


def phase_coordinate_count(*, phases_dir: Path | None = None) -> int:
    """Count coordinate tuples in phase modules (prescription budget)."""
    root = phases_dir or Path(__file__).resolve().parents[1] / "graph" / "phases"
    total = 0
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            total += len(_COORD_TUPLE_RE.findall(text))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple) and len(node.elts) == 2:
                if all(isinstance(elt, ast.Constant) and isinstance(elt.value, int) for elt in node.elts):
                    total += 1
    return total


def evaluate_run(state: AgentState) -> dict[str, float]:
    """Run all evaluators and return metrics dict."""
    return {
        "progress_per_steps": progress_per_steps(state),
        "stuck_frequency": stuck_frequency(state),
        "coherence": coherence_score(state),
        "battle_efficiency": battle_efficiency(state),
        "exploration_coverage": exploration_coverage(state),
        "milestone_completion": milestone_completion(state),
        "stuck_events_per_milestone": stuck_events_per_milestone(state),
        "replan_recovery_rate": replan_recovery_rate(state),
        "phase_coordinate_count": float(phase_coordinate_count()),
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
    scores = evaluate_run(state)
    return {
        "entry_id": dataset_entry["id"],
        "input_match": matches,
        "scores": scores,
        "milestones": state.get("milestones", []),
    }