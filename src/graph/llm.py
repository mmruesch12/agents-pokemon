"""LLM helpers for multi-agent nodes with heuristic fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import AgentState
from src.memory.landmarks import format_landmarks_for_prompt
from src.state.models import GameState

logger = logging.getLogger(__name__)

_MODEL_LOGGED = False

_BATTLE_ACTIONS = ("fight", "run", "switch", "item")


def _match_token(choice: str, candidates: tuple[str, ...] | list[str]) -> str | None:
    """Match LLM output to a candidate by exact token, not substring."""
    normalized = choice.strip().lower().strip("\"'.,")
    if normalized in candidates:
        return normalized
    for token in normalized.split():
        cleaned = token.strip("\"'.,")
        if cleaned in candidates:
            return cleaned
    return None


def get_chat_model():
    """Return ChatOpenAI-compatible model (OpenRouter, xAI Grok or OpenAI) when configured."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    xai_key = os.getenv("XAI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not (openrouter_key or xai_key or openai_key):
        return None
    try:
        from langchain_openai import ChatOpenAI

        if openrouter_key:
            model = (os.getenv("OPENROUTER_MODEL") or "").strip() or "deepseek/deepseek-v4-flash"
            chat = ChatOpenAI(
                model=model,
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=0,
            )
            _log_selected_model("OpenRouter", model)
            return chat
        if xai_key:
            model = (os.getenv("XAI_MODEL") or "").strip() or "grok-4-1-fast-reasoning"
            base_url = (os.getenv("XAI_BASE_URL") or "").strip() or "https://api.x.ai/v1"
            chat = ChatOpenAI(
                model=model,
                api_key=xai_key,
                base_url=base_url,
                temperature=0,
            )
            _log_selected_model("xAI", model)
            return chat
        model = (os.getenv("OPENAI_MODEL") or "").strip() or "gpt-4o-mini"
        chat = ChatOpenAI(model=model, api_key=openai_key, temperature=0)
        _log_selected_model("OpenAI", model)
        return chat
    except Exception as exc:
        logger.warning("LLM init failed: %s", exc)
        return None


def _log_selected_model(provider: str, model: str) -> None:
    """Log chosen provider + model name once per process at INFO."""
    global _MODEL_LOGGED
    if not _MODEL_LOGGED:
        logger.info("LLM using %s (model: %s)", provider, model)
        _MODEL_LOGGED = True


def _llm_invoke_config():
    """Propagate LangGraph RunnableConfig so LLM calls nest under the active node."""
    try:
        from langgraph.config import get_config

        return get_config()
    except RuntimeError:
        return None


def llm_plan(gs: GameState, state: AgentState, landmarks: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Ask Planner LLM for hierarchical subgoals."""
    llm = get_chat_model()
    if llm is None:
        return None

    prompt = (
        f"Map: {gs.player.map_name} ({gs.map_key}) at ({gs.player.x},{gs.player.y})\n"
        f"Party: {gs.party_count}, Badges: {gs.total_badges}\n"
        f"Battle: {gs.battle.in_battle}\n"
    )
    landmark_text = format_landmarks_for_prompt(landmarks or [])
    prompt = (
        f"Map: {gs.player.map_name} ({gs.map_key}) at ({gs.player.x},{gs.player.y})\n"
        f"Party: {gs.party_count}, Badges: {gs.total_badges}\n"
        f"Battle: {gs.battle.in_battle}\n"
    )
    if landmark_text:
        prompt += f"{landmark_text}\n"
    prompt += (
        f"Current map only — subgoals must be achievable on {gs.player.map_name} now.\n"
        "Reply with exactly 3 short subgoals, one per line, no numbering."
    )
    try:
        resp = llm.invoke(
            [
                SystemMessage(content="You are the Planner for a Pokemon Gold autonomous agent."),
                HumanMessage(content=prompt),
            ],
            config=_llm_invoke_config(),
        )
        lines = [ln.strip("-• ").strip() for ln in resp.content.splitlines() if ln.strip()]
        if lines:
            return {"subgoals": lines[:3], "llm_plan": resp.content[:300]}
    except Exception as exc:
        logger.warning("Planner LLM call failed: %s", exc)
    return None


def llm_navigate(gs: GameState, state: AgentState, candidates: list[str], landmarks: list[dict[str, Any]] | None = None, *, target: tuple[int, int] | None = None) -> str | None:
    """Ask Navigator LLM to pick a direction from candidates."""
    llm = get_chat_model()
    if llm is None or not candidates:
        return None

    landmark_text = format_landmarks_for_prompt(landmarks or [])
    prompt = (
        f"Map: {gs.player.map_name} ({gs.map_key}) at ({gs.player.x},{gs.player.y})\n"
        f"Subgoal: {state.get('active_subgoal', '')}\n"
        f"Party: {gs.party_count} | In dialog: {gs.in_text_box}\n"
        f"Visited count: {len(state.get('visited_positions', []))}\n"
    )
    if landmark_text:
        prompt += f"{landmark_text}\n"
    elif target:
        prompt += f"Navigation target tile: ({target[0]},{target[1]})\n"
    else:
        prompt += "No known landmarks yet — explore to discover locations.\n"
    prompt += (
        f"Valid next path steps (pick one): {', '.join(candidates)}\n"
        "Reply with only the direction word."
    )
    try:
        resp = llm.invoke(
            [
                SystemMessage(content="You are the Navigator for Pokemon Gold. Pick one direction."),
                HumanMessage(content=prompt),
            ],
            config=_llm_invoke_config(),
        )
        matched = _match_token(resp.content, candidates)
        if matched:
            return matched
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
            ],
            config=_llm_invoke_config(),
        )
        matched = _match_token(resp.content, _BATTLE_ACTIONS)
        if matched:
            return matched
    except Exception as exc:
        logger.warning("Battler LLM call failed: %s", exc)
    return None