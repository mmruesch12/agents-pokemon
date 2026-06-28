"""Tests for long-term memory."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.memory.long_term_memory import LongTermMemory


def test_add_and_retrieve_summary():
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_summary("Visited New Bark Town and talked to mom")
        mem.add_summary("Battled wild Sentret on Route 29")
        results = mem.retrieve("Route 29 battle")
        assert any("Route 29" in r for r in results)


def test_add_fact():
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_fact("milestone:Reached Route 29")
        assert "milestone:Reached Route 29" in mem.get_facts()


def test_summarize_history():
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        summary = mem.summarize_history(["navigate:right", "navigate:up"])
        assert "navigate" in summary


def test_hydrate_state_merges_checkpoint_and_disk_landmarks():
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_landmark(
            {
                "id": "elms_lab_entrance",
                "name": "Elm's Lab entrance",
                "map_key": "24:4",
                "x": 6,
                "y": 3,
                "kind": "building_entrance",
            }
        )
        state = {
            "known_landmarks": [
                {
                    "id": "elms_lab_interior",
                    "name": "Elm's Lab",
                    "map_key": "24:5",
                    "x": 4,
                    "y": 2,
                    "kind": "interior",
                }
            ]
        }
        hydrated = mem.hydrate_state(state)
        ids = {entry["id"] for entry in hydrated["known_landmarks"]}
        assert ids == {"elms_lab_entrance", "elms_lab_interior"}


def test_add_landmark_persists_to_disk():
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_landmark(
            {
                "id": "elms_lab_entrance",
                "name": "Elm's Lab",
                "map_key": "24:5",
                "x": 5,
                "y": 2,
                "kind": "interior",
            }
        )
        reloaded = LongTermMemory(data_dir=Path(tmp))
        assert reloaded.get_landmarks()[0]["name"] == "Elm's Lab"
        assert any("Lab" in str(entry) for entry in reloaded.retrieve_landmarks("lab"))