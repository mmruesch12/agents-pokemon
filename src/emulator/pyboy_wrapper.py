"""Headless PyBoy wrapper for Pokemon Gold/Silver."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from src.state.gold_state_reader import GoldStateReader, PyBoyMemoryReader
from src.state.models import GameState

logger = logging.getLogger(__name__)

Button = Literal["a", "b", "start", "select", "up", "down", "left", "right"]

BUTTON_MAP = {
    "a": "a",
    "b": "b",
    "start": "start",
    "select": "select",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}


class PyBoyWrapper:
    """Control plane wrapper around PyBoy emulator."""

    def __init__(
        self,
        rom_path: str | Path,
        *,
        window: str = "headless",
        save_dir: str | Path = "saves",
    ):
        from pyboy import PyBoy

        self.rom_path = Path(rom_path)
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {self.rom_path}")

        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self._pyboy = PyBoy(str(self.rom_path), window=window)
        self._frame_count = 0
        self._reader = GoldStateReader(PyBoyMemoryReader(self._pyboy))

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def tick(self, frames: int = 1) -> int:
        """Advance emulation by N frames."""
        for _ in range(frames):
            if not self._pyboy.tick():
                break
            self._frame_count += 1
        return self._frame_count

    def advance_frames(self, n: int) -> int:
        return self.tick(n)

    def press_button(self, button: Button, *, hold_frames: int = 2) -> None:
        """Press and release a Game Boy button."""
        key = BUTTON_MAP[button]
        self._pyboy.button_press(key)
        self.tick(hold_frames)
        self._pyboy.button_release(key)
        self.tick(1)

    def get_game_state(self) -> GameState:
        self._reader._frame_count = self._frame_count
        return self._reader.read()

    def save_state(self, name: str) -> Path:
        path = self.save_dir / f"{name}.state"
        with open(path, "wb") as f:
            self._pyboy.save_state(f)
        logger.info("Saved emulator state to %s", path)
        return path

    def load_state(self, name: str) -> None:
        path = self.save_dir / f"{name}.state"
        if not path.exists():
            raise FileNotFoundError(f"Save state not found: {path}")
        with open(path, "rb") as f:
            self._pyboy.load_state(f)
        logger.info("Loaded emulator state from %s", path)

    def screenshot(self) -> bytes:
        import io

        img = self._pyboy.screen.image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def stop(self) -> None:
        self._pyboy.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()