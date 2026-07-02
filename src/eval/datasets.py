"""Evaluation datasets for progress tracking."""

from __future__ import annotations

from typing import Any

EARLY_GAME_DATASET: list[dict[str, Any]] = [
    {
        "id": "new_bark_start",
        "description": "Player in New Bark Town at start",
        "input": {"map_group": 0, "map_id": 0, "x": 5, "y": 8},
        "expected_phase": "explore",
        "milestone_targets": ["Enter Route 29"],
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
    {
        "id": "elms_lab_starter",
        "description": "Player in Elm's lab before choosing starter",
        "input": {"map_group": 24, "map_id": 5, "x": 4, "y": 8, "party_count": 0},
        "expected_phase": "explore",
        "milestone_targets": ["Entered Elm's lab", "Chose first Pokemon"],
    },
    {
        "id": "mr_pokemon_house",
        "description": "Player at Mr. Pokemon's house",
        "input": {"map_group": 26, "map_id": 10, "x": 5, "y": 5},
        "expected_phase": "explore",
        "milestone_targets": ["Reached Mr. Pokemon's house"],
    },
    {
        "id": "rival_battle",
        "description": "First rival trainer battle in Elm's lab",
        "input": {
            "map_group": 24,
            "map_id": 5,
            "x": 4,
            "y": 8,
            "in_battle": True,
            "battle_mode": 2,
        },
        "expected_phase": "battle",
        "milestone_targets": ["First rival battle"],
    },
]


def get_dataset(name: str = "early_game") -> list[dict[str, Any]]:
    if name == "early_game":
        return EARLY_GAME_DATASET
    return []