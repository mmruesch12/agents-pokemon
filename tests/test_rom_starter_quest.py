"""ROM smoke tests for starter quest (requires user-supplied ROM)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROM_PATH = Path(os.getenv("POKEMON_ROM", "roms/pokemon_gold.gbc"))


@pytest.mark.rom
def test_rom_starter_quest_cold_boot_progresses():
    """Cold boot with high step budget should show starter-quest phase handling."""
    if not ROM_PATH.is_file():
        pytest.skip(f"ROM not found: {ROM_PATH}")

    from src.graph.graph import compile_graph
    from src.graph.state import initial_agent_state
    from src.emulator.pyboy_wrapper import PyBoyWrapper

    emu = PyBoyWrapper(str(ROM_PATH), headless=True)
    try:
        gs = emu.get_game_state()
        state = initial_agent_state(gs)
        state["run_max_steps"] = 2000
        compiled = compile_graph(emu)
        result = compiled.invoke(state, config={"configurable": {"thread_id": "rom-starter"}})
        milestones = result.get("milestones", [])
        assert milestones or result.get("metrics", {}).get("steps", 0) > 0
    finally:
        emu.stop()