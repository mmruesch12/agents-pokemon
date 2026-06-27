"""Helper for running emulation sessions (headless by default; supports headed via window= or headed=)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from src.emulator.pyboy_wrapper import PyBoyWrapper
from src.state.models import GameState

logger = logging.getLogger(__name__)


def run_headless_session(
    rom_path: str | Path,
    *,
    steps: int = 60,
    on_step: Callable[[int, GameState], None] | None = None,
    save_dir: str | Path = "saves",
    headed: bool = False,
    window: str | None = None,
) -> GameState:
    """Run an emulation session for N frame ticks.

    Headless by default (window="null"). Pass headed=True or window="SDL2"
    to enable visible emulator window for watching the agent.
    """
    effective_window = window if window is not None else ("SDL2" if headed else "null")
    with PyBoyWrapper(rom_path, window=effective_window, save_dir=save_dir) as emu:
        state = emu.get_game_state()
        for i in range(steps):
            emu.tick(1)
            state = emu.get_game_state()
            if on_step:
                on_step(i + 1, state)
        return state


def smoke_test_rom(rom_path: str | Path, *, frames: int = 60, headed: bool = False, window: str | None = None) -> dict:
    """Quick smoke test: load ROM, advance frames, read state.

    Headless by default. headed=True or window="SDL2" for visible window.
    """
    effective_window = window if window is not None else ("SDL2" if headed else "null")
    with PyBoyWrapper(rom_path, window=effective_window) as emu:
        emu.tick(frames)
        state = emu.get_game_state()
        return {
            "frames": emu.frame_count,
            "map": state.player.map_name,
            "position": (state.player.x, state.player.y),
            "party_count": state.party_count,
        }