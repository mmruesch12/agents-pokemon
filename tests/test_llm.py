"""Tests for LLM integration layer."""

from __future__ import annotations

from src.graph.llm import _match_token, get_chat_model, llm_battle, llm_navigate, llm_plan
from src.graph.nodes import _navigation_candidates, navigator_node
from src.graph.pathfinding import find_path
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from src.state.models import GameState


def test_match_token_exact_not_substring():
    assert _match_token("right", ["right", "up"]) == "right"
    assert _match_token("upright", ["right", "up"]) is None
    assert _match_token("go right", ["right", "up"]) == "right"
    assert _match_token("flight", ("fight", "run")) is None


def test_get_chat_model_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert get_chat_model() is None


def test_get_chat_model_prefers_xai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
    monkeypatch.setenv("XAI_MODEL", "grok-4-1-fast-reasoning")
    model = get_chat_model()
    assert model is not None
    assert model.model_name == "grok-4-1-fast-reasoning"


def test_llm_plan_heuristic_fallback(new_bark_ram: dict, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    result = llm_plan(gs, state)
    assert result is None


def test_llm_battle_heuristic_fallback(battle_ram: dict, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gs = GoldStateReader(ByteArrayReader(battle_ram)).read()
    result = llm_battle(gs)
    assert result is None


def test_llm_navigate_called_with_path_candidates(new_bark_ram: dict, monkeypatch):
    """Navigator builds candidates even when path is found (LLM hook exercised)."""
    calls: list[list[str]] = []

    def fake_navigate(gs, state, candidates):
        calls.append(candidates)
        return None

    monkeypatch.setattr("src.graph.nodes.llm_navigate", fake_navigate)

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    navigator_node(state)

    assert len(calls) == 1
    assert "right" in calls[0]


def test_navigation_candidates_includes_path(new_bark_ram: dict):
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    path = find_path(gs.player.x, gs.player.y, gs.player.x + 2, gs.player.y, map_key=gs.map_key)
    candidates = _navigation_candidates(gs, (gs.player.x + 2, gs.player.y), path)
    assert candidates[0] == "right"