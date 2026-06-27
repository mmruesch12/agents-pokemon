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