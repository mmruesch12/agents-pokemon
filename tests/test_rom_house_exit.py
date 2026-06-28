"""ROM integration: cold-boot house exit (opt-in via pytest -m rom)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.run.autonomous_runner import AutonomousRunner
from src.state.gold_state_reader import MAP_KEY_NEW_BARK_TOWN

HOUSE_EXIT_MILESTONE = "Left house — New Bark Town"
MAX_STEPS = 100


def _resolve_rom() -> Path | None:
    candidates = [
        Path(os.getenv("ROM_PATH", "roms/pokemon_gold.gb")),
        Path("roms/pokemon_silver.gbc"),
        Path(
            "roms/Pokemon - Silver Version (USA, Europe) (SGB Enhanced) (GB Compatible).gbc"
        ),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


@pytest.fixture(scope="module")
def rom_path() -> Path:
    path = _resolve_rom()
    if path is None:
        pytest.skip("No Pokemon ROM found in roms/")
    return path


@pytest.mark.rom
def test_cold_boot_leaves_starting_house(rom_path: Path, tmp_path_factory):
    """Agent exits Player's House into New Bark Town from a cold boot."""
    base = tmp_path_factory.mktemp("house-exit")
    runner = AutonomousRunner(
        rom_path=rom_path,
        max_steps=MAX_STEPS,
        checkpoint_db=base / "checkpoints.sqlite",
        save_dir=base / "saves",
        thread_id="rom-house-exit",
        langsmith=False,
    )
    result = runner.run()
    assert HOUSE_EXIT_MILESTONE in result["milestones"], (
        f"Expected milestone {HOUSE_EXIT_MILESTONE!r}, got {result['milestones']!r} "
        f"after {result['steps']} steps"
    )
    assert result["final_map_key"] == MAP_KEY_NEW_BARK_TOWN, result
    assert result["final_map_name"] == "New Bark Town"
    assert result["steps"] <= MAX_STEPS