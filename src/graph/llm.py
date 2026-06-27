"""LLM helpers for multi-agent nodes with heuristic fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import AgentState
from src.state.models import GameState

logger = logging.getLogger(__name__)


def get_chat_model():
    """Return ChatOpenAI model if OPENAI_API_KEY is set, else None."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model, temperature=0)
    except Exception as exc:
        logger.warning("LLM init failed: %s", exc)
        return None


def llm_plan(gs: GameState, state: AgentState) -> dict[str, Any] | None:
    """Ask Planner LLM for hierarchical subgoals."""
    llm = get_chat_model()
    if llm is None:
        return None

    prompt = (
        f"Map: {gs.player.map_name} ({gs.player.x},{gs.player.y})\n"
        f"Party: {gs.party_count}, Badges: {gs.total_badges}\n"
        f"Battle: {gs.battle.in_battle}\n"
        f"Goal: progress from New Bark Town toward Route 29 / Violet City.\n"
        "Reply with exactly 3 short subgoals, one per line, no numbering."
    )
    try:
        resp = llm.invoke(
            [
                SystemMessage(content="You are the Planner for a Pokemon Gold autonomous agent."),
                HumanMessage(content=prompt),
            ]
        )
        lines = [ln.strip("-• ").strip() for ln in resp.content.splitlines() if ln.strip()]
        if lines:
            return {"subgoals": lines[:3], "llm_plan": resp.content[:300]}
    except Exception as exc:
        logger.warning("Planner LLM call failed: %s", exc)
    return None


def llm_navigate(gs: GameState, state: AgentState, candidates: list[str]) -> str | None:
    """Ask Navigator LLM to pick a direction from candidates."""
    llm = get_chat_model()
    if llm is None or not candidates:
        return None

    prompt = (
        f"Map: {gs.player.map_name} at ({gs.player.x},{gs.player.y})\n"
        f"Subgoal: {state.get('active_subgoal', '')}\n"
        f"Visited count: {len(state.get('visited_positions', []))}\n"
        f"Choose ONE direction from: {', '.join(candidates)}\n"
        "Reply with only the direction word."
    )
    try:
        resp = llm.invoke(
            [
                SystemMessage(content="You are the Navigator for Pokemon Gold. Pick one direction."),
                HumanMessage(content=prompt),
            ]
        )
        choice = resp.content.strip().lower()
        for c in candidates:
            if c in choice:
                return c
    except Exception as exc:
        logger.warning("Navigator LLM call failed: %s", exc)
    return None


def llm_battle(gs: GameState) -> str | None:
    """Ask Battler LLM for fight/run/switch/item."""
    llm = get_chat_model()
    if llm is None:
        return None

    b = gs.battle
    prompt = (
        f"Wild/trainer battle. Player HP {b.player_active_hp}/{b.player_active_max_hp}, "
        f"Enemy {b.enemy_species_name} HP {b.enemy_hp}/{b.enemy_max_hp}. "
        f"Can run: {b.can_run}. Reply with one word: fight, run, switch, or item."
    )
    try:
        resp = llm.invoke(
            [
                SystemMessage(content="You are the Battler for Pokemon Gold."),
                HumanMessage(content=prompt),
            ]
        )
        action = resp.content.strip().lower()
        for valid in ("fight", "run", "switch", "item"):
            if valid in action:
                return valid
    except Exception as exc:
        logger.warning("Battler LLM call failed: %s", exc)
    return None