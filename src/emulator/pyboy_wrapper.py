"""PyBoy wrapper for Pokemon Gold/Silver (headless by default; supports headed SDL2)."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

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
        window: str = "null",
        save_dir: str | Path = "saves",
    ):
        """Initialize PyBoy emulator wrapper.

        Args:
            rom_path: Path to the Pokemon ROM (.gb/.gbc).
            window: PyBoy window mode. "null" (default) for headless operation.
                Use "SDL2" for headed/visible emulator window so you can watch
                the agent play. Other valid values: "OpenGL", "GLFW".
            save_dir: Directory for emulator save states.
        """
        from pyboy import PyBoy

        self.rom_path = Path(rom_path)
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {self.rom_path}")

        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        pyboy_args = {"window": window, "sound": False}
        self._pyboy = PyBoy(str(self.rom_path), **pyboy_args)
        if window not in (None, "null"):
            try:
                self._pyboy.set_emulation_speed(1)
            except Exception:
                pass

        self._frame_count = 0
        self._reader = GoldStateReader(PyBoyMemoryReader(self._pyboy))

        self._is_live = window not in (None, "null")
        self._lock: threading.RLock | None = None
        self._live_thread: threading.Thread | None = None
        self._stop_live = threading.Event()
        self._held_key: str | None = None
        self._hold_remaining = 0
        self._ff = False

        if self._is_live:
            self._lock = threading.RLock()
            self._start_live_thread()

    @property
    def frame_count(self) -> int:
        if self._lock:
            with self._lock:
                return self._frame_count
        return self._frame_count

    def read_byte(self, address: int) -> int:
        """Read a WRAM/I/O byte with live-thread lock protection when headed."""
        if self._lock:
            with self._lock:
                return int(self._pyboy.memory[address])
        return int(self._pyboy.memory[address])

    def set_fast_forward(self, enabled: bool) -> None:
        """Accelerate the live background tick loop (headed mode only)."""
        if self._lock:
            with self._lock:
                self._ff = enabled
        else:
            self._ff = enabled

    @contextmanager
    def fast_forward(self) -> Iterator[None]:
        """Context manager for temporary fast-forward during long frame waits."""
        self.set_fast_forward(True)
        try:
            yield
        finally:
            self.set_fast_forward(False)

    def _advance_locked(self, frames: int = 1) -> int:
        for _ in range(frames):
            if not self._pyboy.tick():
                break
            self._frame_count += 1
        return self._frame_count

    def tick(self, frames: int = 1) -> int:
        """Advance emulation by N frames."""
        if self._is_live and self._live_thread and self._live_thread.is_alive():
            assert self._lock is not None
            with self._lock:
                target = self._frame_count + frames
            deadline = time.time() + max(frames / 60.0 + 0.5, 3.0)
            while time.time() < deadline:
                with self._lock:
                    if self._frame_count >= target:
                        return self._frame_count
                time.sleep(0.002)
            with self._lock:
                while self._frame_count < target:
                    self._advance_locked(1)
                return self._frame_count

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
        if self._is_live and self._live_thread and self._live_thread.is_alive():
            assert self._lock is not None
            with self._lock:
                if self._held_key:
                    self._pyboy.button_release(self._held_key)
                self._pyboy.button_press(key)
                self._held_key = key
                self._hold_remaining = hold_frames
            deadline = time.time() + hold_frames / 60.0 + 1.5
            while time.time() < deadline:
                with self._lock:
                    if self._hold_remaining <= 0 and self._held_key is None:
                        break
                time.sleep(0.005)
            with self._lock:
                if self._held_key == key:
                    self._pyboy.button_release(key)
                    self._held_key = None
                    self._hold_remaining = 0
                    self._advance_locked(1)
            return

        self._pyboy.button_press(key)
        self.tick(hold_frames)
        self._pyboy.button_release(key)
        self.tick(1)

    def get_game_state(self) -> GameState:
        if self._lock:
            with self._lock:
                return self._reader.read_at(self._frame_count)
        return self._reader.read_at(self._frame_count)

    def save_state(self, name: str) -> Path:
        path = self.save_dir / f"{name}.state"
        if self._lock:
            with self._lock:
                with open(path, "wb") as f:
                    self._pyboy.save_state(f)
        else:
            with open(path, "wb") as f:
                self._pyboy.save_state(f)
        logger.info("Saved emulator state to %s", path)
        return path

    def load_state(self, name: str) -> None:
        path = self.save_dir / f"{name}.state"
        if not path.exists():
            raise FileNotFoundError(f"Save state not found: {path}")
        if self._lock:
            with self._lock:
                with open(path, "rb") as f:
                    self._pyboy.load_state(f)
                self._frame_count = 0
        else:
            with open(path, "rb") as f:
                self._pyboy.load_state(f)
            self._frame_count = 0
        logger.info("Loaded emulator state from %s", path)

    def screenshot(self) -> bytes:
        import io

        if self._lock:
            with self._lock:
                img = self._pyboy.screen.image
        else:
            img = self._pyboy.screen.image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def stop(self) -> None:
        self._stop_live.set()
        if self._live_thread and self._live_thread.is_alive():
            self._live_thread.join(timeout=1.0)
        self._pyboy.stop()

    def _start_live_thread(self) -> None:
        self._live_thread = threading.Thread(
            target=self._live_loop, daemon=True, name="pyboy-live"
        )
        self._live_thread.start()

    def _live_loop(self) -> None:
        assert self._lock is not None
        while not self._stop_live.is_set():
            with self._lock:
                burst = 8 if self._ff else 1
                if self._held_key and self._hold_remaining > 0:
                    steps = min(self._hold_remaining, burst)
                    self._advance_locked(steps)
                    self._hold_remaining -= steps
                    if self._hold_remaining <= 0:
                        self._pyboy.button_release(self._held_key)
                        self._held_key = None
                        self._advance_locked(1)
                else:
                    self._advance_locked(burst)
                ff_sleep = self._ff
            time.sleep(0.001 if ff_sleep else 0.016)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()