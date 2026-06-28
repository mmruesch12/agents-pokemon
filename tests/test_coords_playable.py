"""Tests for coordinate validity heuristics."""

from __future__ import annotations

from src.state.gold_state_reader import coords_playable


def test_coords_playable_accepts_spawn_tile():
    assert coords_playable(3, 3, facing=0) is True


def test_coords_playable_rejects_garbage_coords():
    assert coords_playable(93, 55, facing=255) is False


def test_coords_playable_rejects_invalid_facing_only():
    assert coords_playable(3, 3, facing=255) is False