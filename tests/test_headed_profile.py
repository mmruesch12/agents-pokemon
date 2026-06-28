"""Tests for smooth headed watch profile (owner thread, MemorySaver, tracing)."""

from __future__ import annotations

import os
import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.emulator.pyboy_wrapper import PyBoyWrapper, _OwnerCommand, _OwnerDispatcher
from src.graph.graph import compile_graph
from src.run._langsmith import configure_tracing
from src.run.autonomous_runner import AutonomousRunner


class _FakePyBoy:
    """Minimal PyBoy stand-in for ROM-free wrapper tests."""

    tick_calls = 0
    init_threads: list[str] = []

    def __init__(self, _rom_path: str, **kwargs):
        _FakePyBoy.init_threads.append(threading.current_thread().name)
        self.window = kwargs.get("window", "null")
        self._memory = bytearray(0x10000)
        self._saved: bytes | None = None
        self._tick_n = 0

    def tick(self) -> bool:
        self._tick_n += 1
        _FakePyBoy.tick_calls += 1
        return True

    def button_press(self, _key: str) -> None:
        pass

    def button_release(self, _key: str) -> None:
        pass

    def set_emulation_speed(self, _speed: int) -> None:
        pass

    def save_state(self, handle) -> None:
        self._saved = b"fake-state"
        handle.write(self._saved)

    def load_state(self, handle) -> None:
        self._saved = handle.read()

    def stop(self) -> None:
        pass

    @property
    def screen(self):
        class _Screen:
            @property
            def image(self):
                from PIL import Image

                return Image.new("RGB", (160, 144))

        return _Screen()

    @property
    def memory(self):
        return self._memory


class _MutatingRamPyBoy(_FakePyBoy):
    """PyBoy fake whose tick() mutates WRAM map bytes (exercises owner-thread reads)."""

    MAP_GROUP = 0xDA00
    MAP_NUMBER = 0xDA01

    def tick(self) -> bool:
        self._tick_n += 1
        _FakePyBoy.tick_calls += 1
        mem = self.memory
        if self._tick_n >= 6:
            mem[self.MAP_GROUP] = 24
            mem[self.MAP_NUMBER] = 7
        if self._tick_n == 4:
            mem[self.MAP_GROUP] = 7
        return True


@pytest.fixture
def fake_rom(tmp_path):
    rom = tmp_path / "test.gb"
    rom.write_bytes(b"\x00" * 64)
    return rom


@pytest.fixture
def fake_pyboy(monkeypatch):
    _FakePyBoy.tick_calls = 0
    _FakePyBoy.init_threads = []
    import pyboy

    monkeypatch.setattr(pyboy, "PyBoy", _FakePyBoy)


@pytest.fixture
def mutating_pyboy(monkeypatch):
    _FakePyBoy.tick_calls = 0
    _FakePyBoy.init_threads = []
    import pyboy

    monkeypatch.setattr(pyboy, "PyBoy", _MutatingRamPyBoy)


def test_pyboy_wrapper_headless_is_not_live(fake_rom, fake_pyboy):
    with PyBoyWrapper(fake_rom, window="null") as wrapper:
        assert wrapper._is_live is False
        assert wrapper._lock is None
        assert wrapper._live_thread is None


def test_headed_pyboy_created_on_owner_thread(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert wrapper._is_live is True
        assert wrapper._live_thread is not None
        assert wrapper._live_thread.name == "pyboy-owner"
        assert wrapper._live_thread.is_alive()
        assert _FakePyBoy.init_threads == ["pyboy-owner"]
        assert threading.current_thread().name != "pyboy-owner"
    finally:
        wrapper.stop()


def test_owner_dispatcher_idle_handler_without_commands():
    """Isolated queue test: idle handler runs when no commands are pending."""
    idle_calls: list[int] = []
    idle_ready = threading.Event()

    def idle() -> None:
        idle_calls.append(1)
        if len(idle_calls) >= 3:
            idle_ready.set()

    def execute(_cmd: _OwnerCommand) -> None:
        raise AssertionError("execute should not run during idle-only test")

    dispatcher = _OwnerDispatcher(thread_name="test-owner")
    dispatcher.start(setup=lambda: None, execute=execute, idle=idle, ff_getter=lambda: False)
    dispatcher.wait_ready(timeout=2.0)
    try:
        assert idle_ready.wait(timeout=2.0), f"idle handler never reached 3 calls: {idle_calls}"
        assert len(idle_calls) >= 3
    finally:
        dispatcher.stop()


def test_owner_dispatcher_dispatch_round_trip():
    """Isolated queue test: command posts, blocks caller, returns result."""
    results: list[str] = []

    def execute(cmd: _OwnerCommand) -> None:
        results.append(cmd.op)
        cmd.result_slot["result"] = cmd.args[0] * 2

    dispatcher = _OwnerDispatcher(thread_name="test-dispatch")
    dispatcher.start(setup=lambda: None, execute=execute, idle=lambda: None, ff_getter=lambda: False)
    dispatcher.wait_ready(timeout=2.0)
    try:
        assert dispatcher.dispatch("echo", 21) == 42
        assert results == ["echo"]
    finally:
        dispatcher.stop()


def test_owner_dispatcher_raises_when_thread_dies():
    """Dead owner thread must fail fast instead of hanging until timeout."""
    dispatcher = _OwnerDispatcher(thread_name="test-dead")
    dispatcher._fatal_error = RuntimeError("simulated death")
    dispatcher._stop.set()
    with pytest.raises(RuntimeError, match="died"):
        dispatcher.dispatch("tick", 1, timeout=0.5)


def test_headed_idle_ticks_advance_frame_count(fake_rom, monkeypatch):
    """Integration: owner idle loop advances frames without explicit tick() calls."""
    idle_ready = threading.Event()

    class _SignallingPyBoy(_FakePyBoy):
        def tick(self) -> bool:
            result = super().tick()
            if _FakePyBoy.tick_calls >= 3:
                idle_ready.set()
            return result

    _FakePyBoy.tick_calls = 0
    _FakePyBoy.init_threads = []
    import pyboy

    monkeypatch.setattr(pyboy, "PyBoy", _SignallingPyBoy)

    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert wrapper._owner_thread is not None
        assert wrapper._owner_thread.is_alive()
        assert idle_ready.wait(timeout=2.0), f"owner idle ticks={_FakePyBoy.tick_calls}"
        assert wrapper.frame_count >= 3
        assert _FakePyBoy.tick_calls >= 3
    finally:
        wrapper.stop()


def test_pyboy_wrapper_headed_tick_via_command_queue(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        start = wrapper.frame_count
        result = wrapper.tick(5)
        assert result == start + 5
        assert wrapper.frame_count == start + 5
        assert isinstance(wrapper._cmd_queue, queue.Queue)
    finally:
        wrapper.stop()


def test_pyboy_wrapper_headed_fast_forward_via_queue(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        with wrapper.fast_forward():
            wrapper.tick(16)
        assert wrapper.frame_count == 16
    finally:
        wrapper.stop()


def test_pyboy_wrapper_fast_forward_flag_on_owner(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        wrapper.set_fast_forward(True)
        assert wrapper._dispatch("get_ff") is True
        wrapper.set_fast_forward(False)
        assert wrapper._dispatch("get_ff") is False
    finally:
        wrapper.stop()


def test_pyboy_wrapper_fast_forward_context_manager(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        with wrapper.fast_forward():
            assert wrapper._dispatch("get_ff") is True
        assert wrapper._dispatch("get_ff") is False
    finally:
        wrapper.stop()


def test_pyboy_wrapper_load_state_resets_frame_count(fake_rom, fake_pyboy):
    save_dir = fake_rom.parent / "saves"
    with PyBoyWrapper(fake_rom, window="null", save_dir=save_dir) as wrapper:
        wrapper.tick(25)
        assert wrapper.frame_count == 25
        wrapper.save_state("mid")
        wrapper.tick(10)
        assert wrapper.frame_count == 35
        wrapper.load_state("mid")
        assert wrapper.frame_count == 0
        gs = wrapper.get_game_state()
        assert gs.frame_count == 0


def test_read_byte_observes_ram_after_explicit_tick(fake_rom, mutating_pyboy):
    from src.emulator.bootstrap import read_loaded_map, read_memory_byte
    from src.state.gold_state_reader import ADDR_MAP_GROUP, ADDR_MAP_NUMBER

    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert read_loaded_map(wrapper) == (0, 0)
        wrapper.tick(4)
        assert wrapper.read_byte(0xDA00) == 7
        wrapper.tick(2)
        assert read_loaded_map(wrapper) == (24, 7)
        read_memory_byte(wrapper, ADDR_MAP_GROUP)
        read_memory_byte(wrapper, ADDR_MAP_NUMBER)
    finally:
        wrapper.stop()


def test_headed_uses_owner_thread_not_main_lock(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert wrapper._lock is None
        assert wrapper._live_thread is wrapper._owner_thread
        assert isinstance(wrapper._live_thread, threading.Thread)
    finally:
        wrapper.stop()


def test_compile_graph_accepts_explicit_memory_saver():
    from langgraph.checkpoint.memory import MemorySaver

    saver = MemorySaver()
    graph = compile_graph(None, checkpointer=saver)
    assert graph is not None
    assert graph.checkpointer is saver


def test_compile_graph_sqlite_default_unchanged(tmp_path):
    db = tmp_path / "ckpt.sqlite"
    graph = compile_graph(None, checkpoint_path=db)
    assert graph is not None
    assert graph.checkpointer is not None
    assert db.exists() or db.parent.exists()


def test_compile_graph_explicit_none_skips_sqlite(tmp_path):
    db = tmp_path / "should_not_exist.sqlite"
    graph = compile_graph(None, checkpoint_path=None, checkpointer=None)
    assert graph is not None
    assert graph.checkpointer is None
    assert not db.exists()


def test_configure_tracing_disables_for_headed(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    configure_tracing(langsmith=False, headed=True)
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_configure_tracing_enables_when_langsmith(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    configure_tracing(langsmith=True, headed=False)
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGSMITH_HIDE_INPUTS") == "false"


def test_headed_runner_uses_memory_saver_not_sqlite(tmp_path):
    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"\x00" * 32)

    captured: dict[str, object] = {}

    def fake_compile(emu, *, checkpoint_path=None, checkpointer=None):
        captured["checkpoint_path"] = checkpoint_path
        captured["checkpointer"] = checkpointer
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "metrics": {"steps": 1},
            "milestones": [],
            "game_state": {"player": {"map_name": "x", "x": 0, "y": 0}},
            "last_action": "none",
            "phase": "explore",
            "bootstrap_complete": True,
            "stuck_count": 0,
        }
        mock_graph.get_state.side_effect = Exception("no checkpoint")
        return mock_graph

    with (
        patch("src.emulator.pyboy_wrapper.PyBoyWrapper") as mock_wrapper_cls,
        patch("src.run.autonomous_runner.compile_graph", side_effect=fake_compile),
        patch("src.tools.pokemon_tools.bind_emulator"),
        patch("src.run.autonomous_runner.create_initial_state") as mock_init,
        patch("src.run.autonomous_runner.evaluate_run", return_value={}),
    ):
        emu = MagicMock()
        emu.frame_count = 0
        emu.get_game_state.return_value = MagicMock(model_dump=lambda: {})
        mock_wrapper_cls.return_value.__enter__.return_value = emu
        mock_init.return_value = {
            "metrics": {"steps": 0},
            "milestones": [],
            "game_state": {},
            "bootstrap_complete": True,
            "phase": "explore",
        }

        runner = AutonomousRunner(rom_path=rom, max_steps=1, headed=True, save_dir=tmp_path / "saves")
        runner.run()

    assert captured.get("checkpoint_path") is None
    assert captured["checkpointer"] is not None
    assert type(captured["checkpointer"]).__name__ in ("InMemorySaver", "MemorySaver")


def test_headless_runner_uses_sqlite_path(tmp_path):
    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"\x00" * 32)
    ckpt = tmp_path / "data" / "checkpoints.sqlite"

    captured: dict[str, object] = {}

    def fake_compile(emu, *, checkpoint_path=None, checkpointer=None):
        captured["checkpoint_path"] = checkpoint_path
        captured["checkpointer"] = checkpointer
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "metrics": {"steps": 1},
            "milestones": [],
            "game_state": {"player": {}},
            "last_action": "none",
            "phase": "explore",
            "bootstrap_complete": True,
            "stuck_count": 0,
        }
        mock_graph.get_state.side_effect = Exception("no checkpoint")
        return mock_graph

    with (
        patch("src.emulator.pyboy_wrapper.PyBoyWrapper") as mock_wrapper_cls,
        patch("src.run.autonomous_runner.compile_graph", side_effect=fake_compile),
        patch("src.tools.pokemon_tools.bind_emulator"),
        patch("src.run.autonomous_runner.create_initial_state") as mock_init,
        patch("src.run.autonomous_runner.evaluate_run", return_value={}),
    ):
        emu = MagicMock()
        mock_wrapper_cls.return_value.__enter__.return_value = emu
        mock_init.return_value = {
            "metrics": {"steps": 0},
            "milestones": [],
            "game_state": {},
            "bootstrap_complete": True,
            "phase": "explore",
        }

        runner = AutonomousRunner(
            rom_path=rom, max_steps=1, headed=False, checkpoint_db=ckpt, save_dir=tmp_path / "saves"
        )
        runner.run()

    assert captured["checkpointer"] is None
    assert captured["checkpoint_path"] == ckpt


def test_resolve_thread_id_skips_sqlite_when_headed(tmp_path):
    ckpt = tmp_path / "checkpoints.sqlite"
    import sqlite3

    conn = sqlite3.connect(str(ckpt))
    conn.execute(
        "CREATE TABLE checkpoints (checkpoint_id INTEGER PRIMARY KEY, thread_id TEXT)"
    )
    conn.execute("INSERT INTO checkpoints (thread_id) VALUES ('from-sqlite')")
    conn.commit()
    conn.close()

    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"\x00" * 32)
    runner = AutonomousRunner(rom_path=rom, checkpoint_db=ckpt, headed=True, thread_id="default")
    assert runner._resolve_thread_id("latest") == "default"

    runner_headless = AutonomousRunner(rom_path=rom, checkpoint_db=ckpt, headed=False, thread_id="default")
    assert runner_headless._resolve_thread_id("latest") == "from-sqlite"


def test_seed_state_from_loaded_emulator_marks_bootstrap_complete(tmp_path):
    from src.state.gold_state_reader import ADDR_MAP_GROUP, ADDR_MAP_NUMBER
    from tests.fake_emulator import MutableRamEmulator

    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"\x00" * 32)
    emu = MutableRamEmulator(
        {
            ADDR_MAP_GROUP: 24,
            ADDR_MAP_NUMBER: 7,
            0xD163: 1,
        }
    )

    runner = AutonomousRunner(rom_path=rom, headed=True)
    state = runner._seed_state_from_loaded_emulator(emu, "final_42")
    assert state["bootstrap_complete"] is True
    assert state["phase"] == "explore"
    assert state["game_state"]["player"]["map_group"] == 24
    assert state["game_state"]["player"]["map_id"] == 7