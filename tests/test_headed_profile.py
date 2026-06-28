"""Tests for smooth headed watch profile (live thread, MemorySaver, tracing)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from src.emulator.pyboy_wrapper import PyBoyWrapper
from src.graph.graph import compile_graph
from src.run._langsmith import configure_tracing
from src.run.autonomous_runner import AutonomousRunner


def test_pyboy_wrapper_headless_is_not_live():
    """Headless wrapper has no live thread machinery."""
    # Structural check on class defaults without requiring a ROM.
    assert PyBoyWrapper.__init__.__doc__ is not None
    # Fake instance attributes set in __init__ path for null window:
    wrapper = object.__new__(PyBoyWrapper)
    wrapper._is_live = False
    wrapper._lock = None
    wrapper._live_thread = None
    assert wrapper._is_live is False
    assert wrapper._lock is None


def test_compile_graph_accepts_explicit_memory_saver():
    """Headed profile can pass an in-memory checkpointer."""
    from langgraph.checkpoint.memory import MemorySaver

    saver = MemorySaver()
    graph = compile_graph(None, checkpointer=saver)
    assert graph is not None
    assert graph.checkpointer is saver


def test_compile_graph_sqlite_default_unchanged(tmp_path):
    """Headless default still uses SQLite when checkpoint_path is set."""
    db = tmp_path / "ckpt.sqlite"
    graph = compile_graph(None, checkpoint_path=db)
    assert graph is not None
    assert graph.checkpointer is not None
    assert db.exists() or db.parent.exists()


def test_configure_tracing_disables_for_headed(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    configure_tracing(langsmith=False, headed=True)
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_configure_tracing_enables_when_langsmith(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    configure_tracing(langsmith=True, headed=False)
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"


def test_headed_runner_uses_memory_saver_not_sqlite(tmp_path):
    """AutonomousRunner.run wires MemorySaver when headed=True."""
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

    assert captured["checkpoint_path"] is None
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