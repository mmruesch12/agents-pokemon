"""Fast-start snapshots: bedroom, lab desk, arbitrary emulator states."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.emulator.bootstrap import (
    LAB_DESK_START_STATE,
    ROUTE_29_GATE_APPROACH_STATE,
    install_lab_start_from_save,
    install_route_29_gate_from_save,
    seed_agent_state_for_map,
    seed_lab_agent_state,
    seed_route_29_agent_state,
)
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
)
from src.state.models import GameState


def test_seed_route_29_west_entrance_sets_cross_subgoal():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 59, "y": 8},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = initial_agent_state(gs)
    result = seed_route_29_agent_state(state, gs)
    assert result["house_exit_complete"] is True
    assert result["active_subgoal"] == "Cross Route 29"
    assert starter_quest.MILESTONE_CHOSE_STARTER in result["milestones"]
    assert "Reached Route 29" in result["milestones"]
    assert MAP_KEY_ROUTE_29 in result["maps_visited"]
    assert MAP_KEY_NEW_BARK_TOWN in result["maps_visited"]


def test_seed_agent_state_for_map_route_29_post_starter():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 59, "y": 8},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = initial_agent_state(gs)
    result = seed_agent_state_for_map(state, gs)
    assert result["active_subgoal"] == "Cross Route 29"


def test_seed_new_bark_post_starter_sets_route_subgoal():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 0, "y": 8},
        party_count=1,
        raw_metadata={"has_starter": True},
    )
    state = initial_agent_state(gs)
    result = seed_agent_state_for_map(state, gs)
    assert result["house_exit_complete"] is True
    assert result["active_subgoal"] == "Enter Route 29"
    assert MAP_KEY_NEW_BARK_TOWN in result["maps_visited"]


def test_seed_lab_agent_state_sets_starter_quest_flags():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 2},
        party_count=0,
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    result = seed_lab_agent_state(state, gs)
    assert result["bootstrap_complete"] is True
    assert result["house_exit_complete"] is True
    assert starter_quest.MILESTONE_ENTERED_LAB in result["milestones"]
    assert MAP_KEY_ELMS_LAB in result["maps_visited"]
    assert "Elm" in result["active_subgoal"]


def test_repair_elms_lab_clears_desynced_starter_flag():
    from src.emulator.bootstrap import repair_elms_lab_snapshot
    from src.state.gold_state_reader import ADDR_EVENT_FLAGS, ADDR_FACING, ByteArrayReader, GoldStateReader
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM

    class _Emu:
        def __init__(self, mem: dict[int, int]):
            self._mem = mem

        def read_byte(self, address: int) -> int:
            return self._mem.get(address, 0)

        def write_byte(self, address: int, value: int) -> None:
            self._mem[address] = value & 0xFF

        def get_game_state(self) -> GameState:
            return GoldStateReader(ByteArrayReader(self._mem)).read()

    mem: dict[int, int] = {
        0xDA00: 24,
        0xDA01: 5,
        0xDA02: 3,
        0xDA03: 5,
        ADDR_FACING: 7,
    }
    mem[ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)] = 1 << (
        EVENT_GOT_A_POKEMON_FROM_ELM % 8
    )
    emu = _Emu(mem)
    gs = emu.get_game_state()
    assert gs.raw_metadata.get("has_starter") is True
    repaired = repair_elms_lab_snapshot(emu, gs)
    assert repaired.raw_metadata.get("has_starter") is False
    assert repaired.player.facing == 12


def test_seed_lab_agent_state_at_ball_row_sets_ball_subgoal():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 5, "y": 3, "facing": 0},
        party_count=0,
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    result = seed_lab_agent_state(state, gs)
    assert "Poke Ball" in result["active_subgoal"]


def test_install_route_29_gate_from_save(tmp_path: Path):
    source = tmp_path / "stuck_113.state"
    source.write_bytes(b"gate-approach")
    target = install_route_29_gate_from_save(
        "stuck_113",
        save_dir=tmp_path,
        target_name=ROUTE_29_GATE_APPROACH_STATE,
    )
    assert target == tmp_path / f"{ROUTE_29_GATE_APPROACH_STATE}.state"
    assert target.read_bytes() == b"gate-approach"


def test_install_lab_start_from_save(tmp_path: Path):
    source = tmp_path / "final_200.state"
    source.write_bytes(b"fake-state")
    target = install_lab_start_from_save(
        "final_200",
        save_dir=tmp_path,
        target_name=LAB_DESK_START_STATE,
    )
    assert target == tmp_path / f"{LAB_DESK_START_STATE}.state"
    assert target.read_bytes() == b"fake-state"


def test_start_lab_rejects_resume():
    from src.run.autonomous_runner import AutonomousRunner

    runner = AutonomousRunner(
        rom_path="roms/pokemon_gold.gb",
        max_steps=10,
        start_lab=True,
    )
    with pytest.raises(ValueError, match="Fast-start"):
        runner.run(resume="latest")


def test_emulator_state_rejects_start_bedroom():
    from src.run.autonomous_runner import AutonomousRunner

    runner = AutonomousRunner(
        rom_path="roms/pokemon_gold.gb",
        max_steps=10,
        start_bedroom=True,
        emulator_state="stuck_200",
    )
    with pytest.raises(ValueError, match="only one"):
        runner.run()