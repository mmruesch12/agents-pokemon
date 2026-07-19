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


def test_graph_invoke_without_emulator_increments_stuck(new_bark_ram: dict):
    """No emulator: position frozen but stuck meter rises on failed navigation."""
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    state["run_max_steps"] = 3

    with tempfile.TemporaryDirectory() as tmp:
        compiled = compile_graph(checkpoint_path=Path(tmp) / "frozen.sqlite")
        result = compiled.invoke(state, config={"configurable": {"thread_id": "frozen"}})
        assert result["metrics"]["steps"] == 3
        assert result["game_state"]["player"]["x"] == 8
        assert result["stuck_count"] >= 2


def test_create_initial_state():
    state = create_initial_state()
    assert state["phase"] == "explore"
    assert len(state["current_plan"]) >= 1


def test_recovery_counters_survive_graph_invoke():
    """LangGraph drops undeclared AgentState keys — recovery counters must be schema fields."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph

    from src.graph.state import AgentState

    def bump(s: dict) -> dict:
        out = dict(s)
        out["outdoor_script_frozen_count"] = 5
        out["recent_nav_positions"] = [("24:3", 1, 2), ("24:3", 1, 2)]
        out["stuck_replan_loops"] = 3
        out["interact_stall_escape_fails"] = 2
        out["stuck_count"] = 7
        return out

    g = StateGraph(AgentState)
    g.add_node("n", bump)
    g.set_entry_point("n")
    g.set_finish_point("n")
    app = g.compile(checkpointer=MemorySaver())
    init = initial_agent_state()
    out = app.invoke(init, config={"configurable": {"thread_id": "recovery-keys"}})
    assert out.get("stuck_count") == 7
    assert out.get("outdoor_script_frozen_count") == 5
    assert out.get("stuck_replan_loops") == 3
    assert out.get("interact_stall_escape_fails") == 2
    assert out.get("recent_nav_positions") == [("24:3", 1, 2), ("24:3", 1, 2)]