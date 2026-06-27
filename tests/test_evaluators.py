"""Tests for evaluation metrics."""

from __future__ import annotations

from src.eval.datasets import get_dataset
from src.eval.evaluators import (
    coherence_score,
    evaluate_against_dataset,
    evaluate_run,
    progress_per_steps,
    stuck_frequency,
)
from src.graph.state import initial_agent_state


def test_progress_per_steps():
    state = initial_agent_state()
    state["visited_positions"] = ["0:0:1:1", "0:0:2:2", "0:0:3:3"]
    state["metrics"] = {"steps": 10}
    assert progress_per_steps(state) == 0.3


def test_stuck_frequency():
    state = initial_agent_state()
    state["stuck_count"] = 5
    state["metrics"] = {"steps": 100}
    assert stuck_frequency(state) == 0.05


def test_coherence_score_proceed():
    state = initial_agent_state()
    state["active_subgoal"] = "Explore New Bark Town"
    state["last_action"] = "navigate_right"
    state["critic_verdict"] = "proceed"
    score = coherence_score(state)
    assert score >= 0.5


def test_evaluate_run_returns_all_metrics():
    state = initial_agent_state()
    scores = evaluate_run(state)
    assert "progress_per_steps" in scores
    assert "stuck_frequency" in scores
    assert "coherence" in scores


def test_dataset_entries():
    dataset = get_dataset("early_game")
    assert len(dataset) >= 4
    state = initial_agent_state({"player": {"map_group": 0, "map_id": 0}})
    result = evaluate_against_dataset(state, dataset[0])
    assert result["entry_id"] == "new_bark_start"