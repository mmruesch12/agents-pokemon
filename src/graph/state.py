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
    short_term_history: list[str]
    visited_positions: list[str]
    memory_retrievals: list[str]
    long_term_facts: list[str]
    known_landmarks: list[dict[str, Any]]
    last_map_transition: dict[str, Any]
    phase: str
    next_node: str
    last_action: str
    last_action_result: dict[str, Any]
    position_before_action: str
    metrics: dict[str, Any]
    stuck_count: int
    session_id: str
    run_max_steps: int
    milestones: list[str]
    critic_verdict: str
    critic_notes: str
    should_replan: bool
    replan_count: int
    maps_visited: list[str]
    badges_at_last_check: int
    bootstrap_complete: bool
    bootstrap_action_index: int
    house_exit_complete: bool
    starter_quest_complete: bool
    early_progression_complete: bool
    lab_desk_dialog_done: bool
    lab_desk_interact_count: int
    lab_desk_script_seen: bool
    lab_steps_without_party: int
    lab_stall_position: str
    error: str


def initial_agent_state(game_state: GameState | dict | None = None) -> AgentState:
    gs = game_state.model_dump() if isinstance(game_state, GameState) else (game_state or {})
    return AgentState(
        messages=[],
        game_state=gs,
        current_plan=["Start new game", "Explore New Bark Town", "Reach Route 29"],
        subgoals=[
            "Leave player house",
            "Visit Elm's lab",
            "Choose starter",
            "Deliver egg and battle rival",
            "Head toward Cherrygrove",
        ],
        active_subgoal="Leave player house",
        short_term_history=[],
        visited_positions=[],
        memory_retrievals=[],
        long_term_facts=[],
        known_landmarks=[],
        last_map_transition={},
        phase="explore",
        next_node="supervisor",
        last_action="",
        last_action_result={},
        position_before_action="",
        metrics={"steps": 0, "badges_earned": 0, "battles_won": 0},
        stuck_count=0,
        session_id="",
        run_max_steps=1,
        milestones=[],
        critic_verdict="proceed",
        critic_notes="",
        should_replan=False,
        replan_count=0,
        maps_visited=[],
        badges_at_last_check=0,
        bootstrap_complete=False,
        bootstrap_action_index=0,
        house_exit_complete=False,
        starter_quest_complete=False,
        early_progression_complete=False,
        error="",
    )


_BOOTSTRAP_META_KEYS = ("movement_ready", "map_loaded", "bootstrap_actions")


def update_game_state(state: AgentState, game_state: GameState) -> AgentState:
    prev_meta = (state.get("game_state") or {}).get("raw_metadata") or {}
    gs_dump = game_state.model_dump()
    meta = dict(gs_dump.get("raw_metadata") or {})
    if not state.get("bootstrap_complete"):
        for key in _BOOTSTRAP_META_KEYS:
            if prev_meta.get(key) is not None:
                meta[key] = prev_meta[key]
    gs_dump["raw_metadata"] = meta
    state["game_state"] = gs_dump
    pos_key = game_state.position_key
    visited = list(state.get("visited_positions", []))
    if pos_key not in visited:
        visited.append(pos_key)
    state["visited_positions"] = visited
    metrics = dict(state.get("metrics", {}))
    metrics["badges_earned"] = game_state.total_badges
    state["metrics"] = metrics
    return state