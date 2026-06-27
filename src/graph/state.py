"""Agent state for LangGraph orchestration."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from src.state.models import GameState


def _merge_lists(left: list, right: list) -> list:
    return left + right


class AgentState(TypedDict, total=False):
    """Rich agent state passed between graph nodes."""

    messages: Annotated[list, add_messages]
    game_state: dict[str, Any]
    current_plan: list[str]
    subgoals: list[str]
    active_subgoal: str
    short_term_history: Annotated[list[str], _merge_lists]
    visited_positions: Annotated[list[str], _merge_lists]
    memory_retrievals: list[str]
    long_term_facts: list[str]
    phase: str
    next_node: str
    last_action: str
    last_action_result: dict[str, Any]
    metrics: dict[str, Any]
    stuck_count: int
    session_id: str
    run_max_steps: int
    milestones: Annotated[list[str], _merge_lists]
    critic_verdict: str
    critic_notes: str
    should_replan: bool
    error: str


def initial_agent_state(game_state: GameState | dict | None = None) -> AgentState:
    gs = game_state.model_dump() if isinstance(game_state, GameState) else (game_state or {})
    return AgentState(
        messages=[],
        game_state=gs,
        current_plan=["Start new game", "Explore New Bark Town", "Reach Route 29"],
        subgoals=["Leave player house", "Visit lab or rival", "Head toward Cherrygrove"],
        active_subgoal="Leave player house",
        short_term_history=[],
        visited_positions=[],
        memory_retrievals=[],
        long_term_facts=[],
        phase="explore",
        next_node="supervisor",
        last_action="",
        last_action_result={},
        metrics={"steps": 0, "badges_earned": 0, "battles_won": 0},
        stuck_count=0,
        session_id="",
        run_max_steps=1,
        milestones=[],
        critic_verdict="proceed",
        critic_notes="",
        should_replan=False,
        error="",
    )


def update_game_state(state: AgentState, game_state: GameState) -> AgentState:
    state["game_state"] = game_state.model_dump()
    pos_key = game_state.position_key
    visited = list(state.get("visited_positions", []))
    if pos_key not in visited:
        visited.append(pos_key)
    state["visited_positions"] = visited
    metrics = dict(state.get("metrics", {}))
    metrics["badges_earned"] = game_state.total_badges
    state["metrics"] = metrics
    return state