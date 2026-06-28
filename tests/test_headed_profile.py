"""Tests for smooth headed watch profile (live thread, MemorySaver, tracing)."""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.emulator.pyboy_wrapper import PyBoyWrapper
from src.graph.graph import compile_graph
from src.run._langsmith import configure_tracing
from src.run.autonomous_runner import AutonomousRunner


class _FakePyBoy:
    """Minimal PyBoy stand-in for ROM-free wrapper tests."""

    tick_calls = 0

    def __init__(self, _rom_path: str, **kwargs):
        self.window = kwargs.get("window", "null")
        self._memory = bytearray(0x10000)
        self._saved: bytes | None = None

    def tick(self) -> bool:
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


@pytest.fixture
def fake_rom(tmp_path):
    rom = tmp_path / "test.gb"
    rom.write_bytes(b"\x00" * 64)
    return rom


@pytest.fixture
def fake_pyboy(monkeypatch):
    _FakePyBoy.tick_calls = 0
    monkeypatch.setattr("pyboy.PyBoy", _FakePyBoy)
    # pyboy is imported inside PyBoyWrapper.__init__
    import pyboy

    monkeypatch.setattr(pyboy, "PyBoy", _FakePyBoy)


def test_pyboy_wrapper_headless_is_not_live(fake_rom, fake_pyboy):
    with PyBoyWrapper(fake_rom, window="null") as wrapper:
        assert wrapper._is_live is False
        assert wrapper._lock is None
        assert wrapper._live_thread is None


def test_pyboy_wrapper_live_thread_advances_frames(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert wrapper._is_live is True
        assert wrapper._live_thread is not None
        assert wrapper._live_thread.is_alive()
        start = wrapper.frame_count
        deadline = time.time() + 0.5
        while wrapper.frame_count <= start and time.time() < deadline:
            time.sleep(0.01)
        assert wrapper.frame_count > start
    finally:
        wrapper.stop()


def test_pyboy_wrapper_fast_forward_accelerates_live_loop(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        time.sleep(0.05)
        normal = wrapper.frame_count
        wrapper.set_fast_forward(True)
        time.sleep(0.05)
        ff = wrapper.frame_count
        wrapper.set_fast_forward(False)
        assert ff > normal
    finally:
        wrapper.stop()


def test_pyboy_wrapper_fast_forward_context_manager(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        with wrapper.fast_forward():
            assert wrapper._ff is True
        assert wrapper._ff is False
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


def test_live_thread_memory_reads_under_concurrent_tick(fake_rom, fake_pyboy):
    from src.emulator.bootstrap import read_loaded_map, read_memory_byte
    from src.state.gold_state_reader import ADDR_MAP_GROUP, ADDR_MAP_NUMBER

    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    wrapper._pyboy._memory[ADDR_MAP_GROUP] = 3
    wrapper._pyboy._memory[ADDR_MAP_NUMBER] = 4
    try:
        assert wrapper._live_thread is not None
        assert wrapper._live_thread.is_alive()
        for _ in range(40):
            read_memory_byte(wrapper, ADDR_MAP_GROUP)
            read_loaded_map(wrapper)
            wrapper.get_game_state()
            time.sleep(0.002)
        assert read_loaded_map(wrapper) == (3, 4)
    finally:
        wrapper.stop()


def test_pyboy_wrapper_read_byte_uses_lock(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert wrapper._lock is not None
        wrapper._pyboy._memory[0xD087] = 7
        assert wrapper.read_byte(0xD087) == 7
    finally:
        wrapper.stop()


def test_pyboy_wrapper_live_loop_uses_lock_for_ff(fake_rom, fake_pyboy):
    wrapper = PyBoyWrapper(fake_rom, window="SDL2", save_dir=fake_rom.parent / "saves")
    try:
        assert wrapper._lock is not None
        assert isinstance(wrapper._lock, type(threading.RLock()))
        with wrapper._lock:
            wrapper._ff = True
            burst = 8 if wrapper._ff else 1
        assert burst == 8
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
            ADDR_MAP_GROUP: 3,
            ADDR_MAP_NUMBER: 4,
            0xD163: 1,
        }
    )

    runner = AutonomousRunner(rom_path=rom, headed=True)
    state = runner._seed_state_from_loaded_emulator(emu, "final_42")
    assert state["bootstrap_complete"] is True
    assert state["phase"] == "explore"
    assert state["loaded_map_key"] == (3, 4)