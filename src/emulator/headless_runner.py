"""Helper for running headless emulation sessions."""

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
) -> GameState:
    """Run a headless emulation session for N frame ticks."""
    with PyBoyWrapper(rom_path, save_dir=save_dir) as emu:
        state = emu.get_game_state()
        for i in range(steps):
            emu.tick(1)
            state = emu.get_game_state()
            if on_step:
                on_step(i + 1, state)
        return state


def smoke_test_rom(rom_path: str | Path, *, frames: int = 60) -> dict:
    """Quick smoke test: load ROM, advance frames, read state."""
    with PyBoyWrapper(rom_path) as emu:
        emu.tick(frames)
        state = emu.get_game_state()
        return {
            "frames": emu.frame_count,
            "map": state.player.map_name,
            "position": (state.player.x, state.player.y),
            "party_count": state.party_count,
        }