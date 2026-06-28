"""Static checks that headed-watch docs match shipped behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.run.autonomous_runner import AutonomousRunner


def test_future_headed_doc_no_stale_sqlite_always_peek():
    text = Path("docs/future-headed-optimizations.md").read_text(encoding="utf-8")
    assert "always peeks sqlite" not in text
    assert "peeks sqlite only when **not** headed" in text


def test_future_headed_doc_mentions_memory_saver_and_live_thread():
    text = Path("docs/future-headed-optimizations.md").read_text(encoding="utf-8")
    assert "_live_loop" in text
    assert "MemorySaver" in text
    assert "read_byte" in text


def test_resolve_thread_id_headed_skips_sqlite_peek(tmp_path):
    import sqlite3

    ckpt = tmp_path / "checkpoints.sqlite"
    conn = sqlite3.connect(str(ckpt))
    conn.execute(
        "CREATE TABLE checkpoints (checkpoint_id INTEGER PRIMARY KEY, thread_id TEXT)"
    )
    conn.execute("INSERT INTO checkpoints (thread_id) VALUES ('from-sqlite')")
    conn.commit()
    conn.close()

    rom = tmp_path / "fake.gb"
    rom.write_bytes(b"\x00" * 32)

    headed = AutonomousRunner(rom_path=rom, checkpoint_db=ckpt, headed=True, thread_id="watch")
    assert headed._resolve_thread_id("latest") == "watch"

    headless = AutonomousRunner(rom_path=rom, checkpoint_db=ckpt, headed=False, thread_id="watch")
    assert headless._resolve_thread_id("latest") == "from-sqlite"