"""StateGraph assembly and compilation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph

from src.graph.nodes import (
    apply_action_node,
    battler_node,
    bootstrap_node,
    critic_node,
    memory_node,
    navigator_node,
    planner_node,
    supervisor_node,
)
from src.graph.router import (
    route_from_battler,
    route_from_bootstrap,
    route_from_critic,
    route_from_memory,
    route_from_navigator,
    route_from_planner,
    route_from_supervisor,
    route_from_apply_action,
)
from src.graph.state import AgentState, initial_agent_state


def _make_apply_action(emulator: Any):
    def node(state: AgentState) -> AgentState:
        return apply_action_node(state, emulator)

    return node


def build_graph(
    emulator: Any = None,
    *,
    checkpoint_path: str | Path | None = None,
) -> StateGraph:
    """Build the multi-agent StateGraph (uncompiled)."""
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("bootstrap", bootstrap_node)
    graph.add_node("planner", planner_node)
    graph.add_node("navigator", navigator_node)
    graph.add_node("battler", battler_node)
    graph.add_node("critic", critic_node)
    graph.add_node("memory", memory_node)
    graph.add_node("apply_action", _make_apply_action(emulator))

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges("supervisor", route_from_supervisor)
    graph.add_conditional_edges("bootstrap", route_from_bootstrap)
    graph.add_conditional_edges("planner", route_from_planner)
    graph.add_conditional_edges("navigator", route_from_navigator)
    graph.add_conditional_edges("battler", route_from_battler)
    graph.add_conditional_edges("apply_action", route_from_apply_action)
    graph.add_conditional_edges("critic", route_from_critic)
    graph.add_conditional_edges("memory", route_from_memory)

    return graph


def compile_graph(
    emulator: Any = None,
    *,
    checkpoint_path: str | Path | None = "data/checkpoints.sqlite",
    checkpointer: Any | None = None,
) -> Any:
    """Compile graph with an optional explicit or SQLite checkpointer."""
    graph = build_graph(emulator, checkpoint_path=checkpoint_path)
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    if checkpoint_path is not None:
        Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
        return graph.compile(checkpointer=SqliteSaver(conn))
    return graph.compile()


def run_graph_step(
    compiled_graph: Any,
    state: AgentState,
    *,
    thread_id: str = "default",
    max_steps_per_invoke: int = 1,
) -> AgentState:
    """Invoke graph for one or more internal steps."""
    config = {"configurable": {"thread_id": thread_id}}
    result = compiled_graph.invoke(state, config=config)
    return result


def create_initial_state(emulator: Any = None) -> AgentState:
    if emulator is not None:
        gs = emulator.get_game_state()
        return initial_agent_state(gs)
    return initial_agent_state()


EXPECTED_NODES = {
    "supervisor",
    "bootstrap",
    "planner",
    "navigator",
    "battler",
    "critic",
    "memory",
    "apply_action",
}