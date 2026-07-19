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


def test_seed_lab_keeps_static_ball_and_desk_landmarks():
    """seed_lab must merge interior discovery, not wipe map-anchor landmarks."""
    from src.graph.navigation_resolve import resolve_navigation_target
    from src.memory.landmarks import (
        ELMS_LAB_BALL_APPROACH_ID,
        ELMS_LAB_DESK_APPROACH_ID,
        find_landmark,
    )

    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 6, "y": 4, "facing": 4},
        party_count=0,
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    # Desk visits so subgoal advances to ball pick.
    state["visited_positions"] = ["24:5:4:2", "24:5:5:2"]
    result = seed_lab_agent_state(state, gs)
    assert find_landmark(
        result.get("known_landmarks", []), landmark_id=ELMS_LAB_BALL_APPROACH_ID
    )
    assert find_landmark(
        result.get("known_landmarks", []), landmark_id=ELMS_LAB_DESK_APPROACH_ID
    )
    # After seed, force ball subgoal via desk visits again (seed may clear at y<=2 only).
    result["visited_positions"] = list(
        set(result.get("visited_positions", [])) | {"24:5:4:2", "24:5:5:2"}
    )
    from src.graph.phases import starter_quest

    starter_quest.sync_subgoals(gs, result)
    assert "Poke Ball" in result["active_subgoal"]
    assert resolve_navigation_target(gs, result) == (6, 4)


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


def test_hard_reload_candidates_exclude_foreign_bed_chain():
    """Hard soft-lock must not teleport to foreign session seeds mid-run."""
    from src.run.autonomous_runner import AutonomousRunner

    plain = AutonomousRunner(rom_path="roms/pokemon_gold.gb", max_steps=1)
    # Before this run stamps free progress, ignore leftover progress_checkpoint*.
    assert plain._hard_reload_candidates(progress_written=False) == []
    names = plain._hard_reload_candidates(progress_written=True)
    assert names == [
        "progress_checkpoint_safe",
        "progress_checkpoint_prev",
        "progress_checkpoint",
    ]
    assert not any(n.startswith("bed_chain") for n in names)
    assert "bedroom_egg_r29" not in names

    bedroom = AutonomousRunner(
        rom_path="roms/pokemon_gold.gb", max_steps=1, start_bedroom=True
    )
    assert "bedroom_start" in bedroom._hard_reload_candidates(progress_written=False)

    emu = AutonomousRunner(
        rom_path="roms/pokemon_gold.gb",
        max_steps=1,
        emulator_state="route29_gate_approach",
    )
    assert "route29_gate_approach" in emu._hard_reload_candidates()