"""Tests for StateGraph construction and compilation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.graph import EXPECTED_NODES, build_graph, compile_graph, create_initial_state
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader


def test_build_graph_has_expected_nodes():
    graph = build_graph()
    node_names = set(graph.nodes.keys())
    assert EXPECTED_NODES.issubset(node_names)


def test_compile_graph_with_checkpointer():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite"
        compiled = compile_graph(checkpoint_path=db_path)
        assert compiled is not None


def test_graph_invoke_without_emulator(new_bark_ram: dict):
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    state["run_max_steps"] = 1

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(checkpoint_path=Path(tmp) / "test.sqlite")
        config = {"configurable": {"thread_id": "test"}}
        result = compiled.invoke(state, config=config)
        assert result["metrics"]["steps"] >= 1
        assert "next_node" in result


def test_create_initial_state():
    state = create_initial_state()
    assert state["phase"] == "explore"
    assert len(state["current_plan"]) >= 1