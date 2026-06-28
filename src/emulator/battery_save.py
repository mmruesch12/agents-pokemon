"""Isolate PyBoy battery-backed .ram/.rtc files for reproducible cold boots."""

from __future__ import annotations

import logging
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


@contextmanager
def isolated_battery_files(rom_path: str | Path) -> Iterator[Path | None]:
    """Move ROM-adjacent .ram/.rtc aside for the duration of a cold boot."""
    rom = Path(rom_path)
    stash = Path(tempfile.mkdtemp(prefix="poke-battery-"))
    moved = False
    try:
        for ext in (".ram", ".rtc"):
            src = rom.with_suffix(rom.suffix + ext)
            if src.exists():
                shutil.move(str(src), str(stash / src.name))
                moved = True
        if moved:
            logger.info("Isolated battery save files for reproducible cold boot")
        yield stash if moved else None
    finally:
        if stash.exists():
            for path in stash.iterdir():
                dest = rom.parent / path.name
                if not dest.exists():
                    shutil.move(str(path), str(dest))
            shutil.rmtree(stash, ignore_errors=True)