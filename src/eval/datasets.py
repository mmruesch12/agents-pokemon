"""Evaluation datasets for progress tracking."""

from __future__ import annotations

from typing import Any

EARLY_GAME_DATASET: list[dict[str, Any]] = [
    {
        "id": "new_bark_start",
        "description": "Player in New Bark Town at start",
        "input": {"map_group": 0, "map_id": 0, "x": 5, "y": 8},
        "expected_phase": "explore",
        "milestone_targets": ["Exit New Bark Town east"],
    },
    {
        "id": "route_29_entry",
        "description": "Player enters Route 29",
        "input": {"map_group": 1, "map_id": 1, "x": 10, "y": 20},
        "expected_phase": "explore",
        "milestone_targets": ["Reached Route 29"],
    },
    {
        "id": "wild_battle",
        "description": "Player in wild battle on Route 29",
        "input": {"in_battle": True, "battle_mode": 1},
        "expected_phase": "battle",
        "milestone_targets": ["Wild Pokemon encounter"],
    },
    {
        "id": "violet_city",
        "description": "Player reaches Violet City",
        "input": {"map_group": 1, "map_id": 4, "x": 15, "y": 20},
        "expected_phase": "explore",
        "milestone_targets": ["Reached Violet City"],
    },
]


def get_dataset(name: str = "early_game") -> list[dict[str, Any]]:
    if name == "early_game":
        return EARLY_GAME_DATASET
    return []