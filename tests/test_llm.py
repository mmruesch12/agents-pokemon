"""Tests for LLM integration layer."""

from __future__ import annotations

import os

from src.graph.llm import get_chat_model, llm_battle, llm_plan
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader


def test_get_chat_model_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_chat_model() is None


def test_llm_plan_heuristic_fallback(new_bark_ram: dict):
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    result = llm_plan(gs, state)
    assert result is None


def test_llm_battle_heuristic_fallback(battle_ram: dict):
    gs = GoldStateReader(ByteArrayReader(battle_ram)).read()
    result = llm_battle(gs)
    assert result is None