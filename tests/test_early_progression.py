"""Tests for early-game progression logic."""

from __future__ import annotations

from src.graph.nodes import _decompose_subgoals, _navigation_target
from src.state.gold_state_reader import ByteArrayReader, GoldStateReader
from src.state.models import GameState


def test_new_bark_subgoals(new_bark_ram: dict):
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    subgoals = _decompose_subgoals(gs)
    assert any("New Bark" in s or "Route 29" in s for s in subgoals)


def test_route_29_subgoals():
    gs = GameState(player={"map_group": 1, "map_id": 1, "x": 10, "y": 20})
    subgoals = _decompose_subgoals(gs)
    assert any("Route 29" in s or "Cherrygrove" in s for s in subgoals)


def test_navigation_target_new_bark(new_bark_ram: dict):
    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    target = _navigation_target(gs)
    assert target[0] > gs.player.x


def test_navigation_target_route_29():
    gs = GameState(player={"map_group": 1, "map_id": 1, "x": 10, "y": 20})
    target = _navigation_target(gs)
    assert target[1] < gs.player.y