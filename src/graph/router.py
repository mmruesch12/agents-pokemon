"""Conditional routing logic for the agent graph."""

from __future__ import annotations

from langgraph.graph import END

from src.graph.state import AgentState

NODE_NAMES = (
    "supervisor",
    "planner",
    "navigator",
    "battler",
    "critic",
    "memory",
    "apply_action",
    "end",
)


def route_from_supervisor(state: AgentState) -> str:
    return state.get("next_node", "navigator")


def route_from_planner(state: AgentState) -> str:
    return state.get("next_node", "navigator")


def route_from_navigator(state: AgentState) -> str:
    return "apply_action"


def route_from_battler(state: AgentState) -> str:
    return "apply_action"


def route_from_apply_action(state: AgentState) -> str:
    return "critic"


def route_from_critic(state: AgentState) -> str:
    return state.get("next_node", "memory")


def route_from_memory(state: AgentState) -> str:
    steps = state.get("metrics", {}).get("steps", 0)
    if steps >= state.get("run_max_steps", 1):
        return END
    return "supervisor"


def should_continue(state: AgentState, max_steps: int) -> str:
    steps = state.get("metrics", {}).get("steps", 0)
    if steps >= max_steps:
        return "end"
    if state.get("error"):
        return "end"
    return "supervisor"