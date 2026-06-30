"""PyBoy wrapper for Pokemon Gold/Silver (headless by default; supports headed SDL2)."""

from __future__ import annotations

import logging
import queue
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

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

_STOP = object()


class _OwnerCommand:
    __slots__ = ("op", "args", "result_slot", "done")

    def __init__(
        self,
        op: str,
        args: tuple[Any, ...],
        result_slot: dict[str, Any],
        done: threading.Event,
    ) -> None:
        self.op = op
        self.args = args
        self.result_slot = result_slot
        self.done = done


class _OwnerDispatcher:
    """Queue-driven single-owner thread dispatcher (testable without PyBoy/SDL)."""

    def __init__(self, *, thread_name: str = "pyboy-owner") -> None:
        self._thread_name = thread_name
        self._cmd_queue: queue.Queue[_OwnerCommand | object] = queue.Queue()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._fatal_error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._execute_command: Callable[[_OwnerCommand], None] | None = None
        self._idle_tick: Callable[[], None] | None = None
        self._ff_getter: Callable[[], bool] = lambda: False

    @property
    def cmd_queue(self) -> queue.Queue[_OwnerCommand | object]:
        return self._cmd_queue

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    def start(
        self,
        *,
        setup: Callable[[], None],
        execute: Callable[[_OwnerCommand], None],
        idle: Callable[[], None],
        ff_getter: Callable[[], bool],
    ) -> None:
        self._execute_command = execute
        self._idle_tick = idle
        self._ff_getter = ff_getter

        def loop() -> None:
            try:
                setup()
            except BaseException as exc:
                self._startup_error = exc
                self._ready.set()
                return
            self._ready.set()
            while not self._stop.is_set():
                try:
                    cmd: _OwnerCommand | object | None = None
                    try:
                        timeout = 0.001 if self._ff_getter() else 0.016
                        cmd = self._cmd_queue.get(timeout=timeout)
                    except queue.Empty:
                        if self._idle_tick is not None:
                            self._idle_tick()
                        continue

                    if cmd is _STOP:
                        break
                    assert isinstance(cmd, _OwnerCommand)
                    assert self._execute_command is not None
                    try:
                        self._execute_command(cmd)
                    except BaseException as exc:
                        cmd.result_slot["error"] = exc
                    finally:
                        cmd.done.set()
                except BaseException as exc:
                    logger.exception("PyBoy owner loop fatal error")
                    self._fatal_error = exc
                    self._stop.set()
                    break

        self._thread = threading.Thread(target=loop, daemon=True, name=self._thread_name)
        self._thread.start()

    def wait_ready(self, timeout: float = 30.0) -> None:
        if not self._ready.wait(timeout):
            self._stop.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            raise RuntimeError(f"{self._thread_name} failed to start within {timeout}s")
        if self._startup_error is not None:
            raise RuntimeError(
                f"{self._thread_name} failed during startup"
            ) from self._startup_error

    def _ensure_alive(self) -> None:
        if self._startup_error is not None:
            raise RuntimeError(
                f"{self._thread_name} failed during startup"
            ) from self._startup_error
        if self._fatal_error is not None:
            raise RuntimeError(f"{self._thread_name} died") from self._fatal_error
        if self._thread is not None and not self._thread.is_alive() and not self._stop.is_set():
            raise RuntimeError(f"{self._thread_name} died unexpectedly")

    def dispatch(self, op: str, *args: Any, timeout: float = 120.0) -> Any:
        self._ensure_alive()
        result_slot: dict[str, Any] = {}
        done = threading.Event()
        self._cmd_queue.put(_OwnerCommand(op, args, result_slot, done))
        if not done.wait(timeout):
            self._ensure_alive()
            raise TimeoutError(
                f"PyBoy owner command '{op}' timed out after {timeout}s "
                f"(thread alive={self._thread.is_alive() if self._thread else False})"
            )
        if "error" in result_slot:
            raise result_slot["error"]
        return result_slot.get("result")

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._cmd_queue.put(_STOP)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


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
        self.rom_path = Path(rom_path)
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {self.rom_path}")

        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self._window = window
        self._is_live = window not in (None, "null")
        self._lock: threading.RLock | None = None
        self._live_thread: threading.Thread | None = None
        self._stop_live = threading.Event()
        self._held_key: str | None = None
        self._hold_remaining = 0
        self._ff = False
        self._frame_count = 0
        self._pyboy: Any = None
        self._reader: GoldStateReader | None = None
        self._dispatcher: _OwnerDispatcher | None = None

        if self._is_live:
            self._dispatcher = _OwnerDispatcher(thread_name="pyboy-owner")
            self._cmd_queue = self._dispatcher.cmd_queue
            self._dispatcher.start(
                setup=lambda: self._owner_setup(str(self.rom_path), window),
                execute=self._execute_owner_command,
                idle=self._owner_idle_tick,
                ff_getter=lambda: self._ff,
            )
            self._owner_thread = self._dispatcher.thread
            self._live_thread = self._owner_thread
            self._dispatcher.wait_ready()
            return

        self._init_direct_pyboy(window)

    def _owner_setup(self, rom_path: str, window: str) -> None:
        from pyboy import PyBoy

        self._pyboy = PyBoy(rom_path, window=window)
        if window not in (None, "null"):
            try:
                self._pyboy.set_emulation_speed(1)
            except Exception:
                pass
        self._reader = GoldStateReader(PyBoyMemoryReader(self._pyboy))

    def _init_direct_pyboy(self, window: str) -> None:
        from pyboy import PyBoy

        self._pyboy = PyBoy(str(self.rom_path), window=window)
        if window not in (None, "null"):
            try:
                self._pyboy.set_emulation_speed(1)
            except Exception:
                pass
        self._reader = GoldStateReader(PyBoyMemoryReader(self._pyboy))

    def _dispatch(self, op: str, *args: Any, timeout: float = 120.0) -> Any:
        assert self._dispatcher is not None
        return self._dispatcher.dispatch(op, *args, timeout=timeout)

    def _execute_owner_command(self, cmd: _OwnerCommand) -> None:
        op = cmd.op
        args = cmd.args
        slot = cmd.result_slot

        if op == "tick":
            slot["result"] = self._owner_tick(int(args[0]))
        elif op == "press_button":
            self._owner_press_button(str(args[0]), int(args[1]))
        elif op == "get_game_state":
            assert self._reader is not None
            slot["result"] = self._reader.read_at(self._frame_count)
        elif op == "read_byte":
            slot["result"] = int(self._pyboy.memory[int(args[0])])
        elif op == "write_byte":
            self._pyboy.memory[int(args[0])] = int(args[1]) & 0xFF
        elif op == "save_state":
            slot["result"] = self._owner_save_state(str(args[0]))
        elif op == "load_state":
            self._owner_load_state(str(args[0]))
        elif op == "screenshot":
            slot["result"] = self._owner_screenshot()
        elif op == "set_fast_forward":
            self._ff = bool(args[0])
        elif op == "get_ff":
            slot["result"] = self._ff
        else:
            raise ValueError(f"Unknown owner command: {op}")

    def _owner_advance(self, frames: int = 1) -> int:
        for _ in range(frames):
            if not self._pyboy.tick():
                break
            self._frame_count += 1
        return self._frame_count

    def _owner_tick(self, frames: int) -> int:
        burst = 8 if self._ff else 1
        remaining = frames
        while remaining > 0:
            batch = min(burst, remaining)
            self._owner_advance(batch)
            remaining -= batch
        return self._frame_count

    def _owner_press_button(self, key: str, hold_frames: int) -> None:
        if self._held_key:
            self._pyboy.button_release(self._held_key)
        self._pyboy.button_press(key)
        self._held_key = key
        self._hold_remaining = hold_frames
        while self._hold_remaining > 0:
            burst = 8 if self._ff else 1
            steps = min(self._hold_remaining, burst)
            self._owner_advance(steps)
            self._hold_remaining -= steps
        if self._held_key == key:
            self._pyboy.button_release(key)
            self._held_key = None
            self._owner_advance(1)

    def _owner_idle_tick(self) -> None:
        burst = 8 if self._ff else 1
        if self._held_key and self._hold_remaining > 0:
            steps = min(self._hold_remaining, burst)
            self._owner_advance(steps)
            self._hold_remaining -= steps
            if self._hold_remaining <= 0:
                self._pyboy.button_release(self._held_key)
                self._held_key = None
                self._owner_advance(1)
        else:
            self._owner_advance(burst)

    def _owner_save_state(self, name: str) -> Path:
        path = self.save_dir / f"{name}.state"
        with open(path, "wb") as f:
            self._pyboy.save_state(f)
        logger.info("Saved emulator state to %s", path)
        return path

    def _owner_load_state(self, name: str) -> None:
        path = self.save_dir / f"{name}.state"
        if not path.exists():
            raise FileNotFoundError(f"Save state not found: {path}")
        with open(path, "rb") as f:
            self._pyboy.load_state(f)
        self._frame_count = 0
        logger.info("Loaded emulator state from %s", path)

    def _owner_screenshot(self) -> bytes:
        import io

        img = self._pyboy.screen.image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @property
    def frame_count(self) -> int:
        # Headed: owner thread updates self._frame_count; read without queue so
        # idle animation is not starved by polling.
        return self._frame_count

    def read_byte(self, address: int) -> int:
        """Read a WRAM/I/O byte with owner-thread protection when headed."""
        if self._is_live:
            return int(self._dispatch("read_byte", address))
        return int(self._pyboy.memory[address])

    def write_byte(self, address: int, value: int) -> None:
        """Write a WRAM/I/O byte with owner-thread protection when headed."""
        if self._is_live:
            self._dispatch("write_byte", address, value)
            return
        self._pyboy.memory[address] = value & 0xFF

    def set_fast_forward(self, enabled: bool) -> None:
        """Accelerate the owner-thread tick loop (headed mode only)."""
        if self._is_live:
            self._dispatch("set_fast_forward", enabled)
            return
        self._ff = enabled

    @contextmanager
    def fast_forward(self) -> Iterator[None]:
        """Context manager for temporary fast-forward during long frame waits."""
        self.set_fast_forward(True)
        try:
            yield
        finally:
            self.set_fast_forward(False)

    def _sync_tick(self, frames: int) -> int:
        """Tick on the calling thread (headless path)."""
        burst = 8 if self._ff else 1
        remaining = frames
        while remaining > 0:
            batch = min(burst, remaining)
            for _ in range(batch):
                if not self._pyboy.tick():
                    return self._frame_count
                self._frame_count += 1
            remaining -= batch
        return self._frame_count

    def tick(self, frames: int = 1) -> int:
        """Advance emulation by N frames."""
        if self._is_live:
            return int(self._dispatch("tick", frames))
        return self._sync_tick(frames)

    def advance_frames(self, n: int) -> int:
        return self.tick(n)

    def press_button(self, button: Button, *, hold_frames: int = 2) -> None:
        """Press and release a Game Boy button."""
        key = BUTTON_MAP[button]
        if self._is_live:
            self._dispatch("press_button", key, hold_frames)
            return
        self._pyboy.button_press(key)
        self.tick(hold_frames)
        self._pyboy.button_release(key)
        self.tick(1)

    def get_game_state(self) -> GameState:
        if self._is_live:
            return self._dispatch("get_game_state")
        assert self._reader is not None
        return self._reader.read_at(self._frame_count)

    def save_state(self, name: str) -> Path:
        if self._is_live:
            return self._dispatch("save_state", name)
        path = self.save_dir / f"{name}.state"
        with open(path, "wb") as f:
            self._pyboy.save_state(f)
        logger.info("Saved emulator state to %s", path)
        return path

    def load_state(self, name: str) -> None:
        if self._is_live:
            self._dispatch("load_state", name)
            return
        path = self.save_dir / f"{name}.state"
        if not path.exists():
            raise FileNotFoundError(f"Save state not found: {path}")
        with open(path, "rb") as f:
            self._pyboy.load_state(f)
        self._frame_count = 0
        logger.info("Loaded emulator state from %s", path)

    def screenshot(self) -> bytes:
        if self._is_live:
            return self._dispatch("screenshot")
        import io

        img = self._pyboy.screen.image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def stop(self) -> None:
        if self._is_live:
            self._stop_live.set()
            assert self._dispatcher is not None
            self._dispatcher.stop()
            return
        if self._pyboy is not None:
            self._pyboy.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()