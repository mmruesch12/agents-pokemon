"""Tests for LangChain tool wrappers."""

from __future__ import annotations

from src.state.models import GameState
from src.tools.pokemon_tools import advance_frames, bind_emulator, get_state, press_button


class FakeEmulator:
    def __init__(self):
        self._frames = 0

    def get_game_state(self) -> GameState:
        return GameState(player={"map_group": 0, "map_id": 0, "x": 5, "y": 5})

    def press_button(self, button: str, *, hold_frames: int = 2) -> None:
        self._frames += hold_frames + 1

    def advance_frames(self, n: int) -> int:
        self._frames += n
        return self._frames

    @property
    def frame_count(self) -> int:
        return self._frames


def test_get_state_tool():
    emu = FakeEmulator()
    bind_emulator(emu)  # type: ignore[arg-type]
    result = get_state.invoke({})
    assert result["player"]["x"] == 5


def test_press_button_tool():
    emu = FakeEmulator()
    bind_emulator(emu)  # type: ignore[arg-type]
    result = press_button.invoke({"button": "a"})
    assert result["button"] == "a"
    assert result["frame_count"] > 0


def test_advance_frames_tool():
    emu = FakeEmulator()
    bind_emulator(emu)  # type: ignore[arg-type]
    result = advance_frames.invoke({"n": 10})
    assert result["frame_count"] == 10