"""Diagnose MeetMomScript progression after 2F->1F warp (cold boot)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.emulator.battery_save import isolated_battery_files
from src.emulator.bootstrap import run_bootstrap
from src.emulator.pyboy_wrapper import PyBoyWrapper
from src.graph.pathfinding import find_path
from src.state.gold_state_reader import (
    ADDR_JOYPAD_DISABLE,
    ADDR_SCRIPT_FLAGS,
    ADDR_SCRIPT_MODE,
    ADDR_SCRIPT_POS,
)
from src.state.script_constants import MOM_SCENE_ENTRY_POS, SCRIPT_FLAG_SCRIPT_RUNNING

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROM = Path("roms/pokemon_silver.gbc")
if not ROM.exists():
    ROM = Path(
        "roms/Pokemon - Silver Version (USA, Europe) (SGB Enhanced) (GB Compatible).gbc"
    )

MUSIC_PLAYING = 0xC0A0  # wMusicPlaying (WRAM0)


def _snap(emu: PyBoyWrapper) -> dict:
    gs = emu.get_game_state()
    meta = gs.raw_metadata or {}
    return {
        "map": gs.map_key,
        "pos": (gs.player.x, gs.player.y),
        "facing": gs.player.facing,
        "script_mode": emu.read_byte(ADDR_SCRIPT_MODE),
        "script_flags": emu.read_byte(ADDR_SCRIPT_FLAGS),
        "script_pos": emu.read_byte(ADDR_SCRIPT_POS)
        | (emu.read_byte(ADDR_SCRIPT_POS + 1) << 8),
        "joypad_disable": emu.read_byte(ADDR_JOYPAD_DISABLE),
        "music": emu.read_byte(MUSIC_PLAYING),
        "mom_flag": meta.get("mom_scene_complete"),
        "init_events": meta.get("init_events_complete"),
    }


def _navigate_to_stairs(emu: PyBoyWrapper) -> None:
    """Walk 2F to stairs at (7,0) using pathfinding."""
    for _ in range(40):
        gs = emu.get_game_state()
        if gs.map_key != "24:7":
            break
        if gs.player.x == 7 and gs.player.y == 0:
            break
        path = find_path(gs.player.x, gs.player.y, 7, 0, map_key="24:7")
        if not path:
            break
        emu.press_button(path[0], hold_frames=12)
        emu.tick(30)


def main() -> int:
    if not ROM.exists():
        logger.error("ROM not found: %s", ROM)
        return 1

    with isolated_battery_files(ROM):
        with PyBoyWrapper(ROM, window="null") as emu:
            result = run_bootstrap(emu, rom_path=ROM)
            logger.info("bootstrap: %s", result)
            logger.info("after bootstrap: %s", _snap(emu))

            _navigate_to_stairs(emu)
            gs = emu.get_game_state()
            logger.info("at stairs: %s", _snap(emu))

            if gs.map_key == "24:7":
                emu.press_button("up", hold_frames=12)
                emu.tick(90)

            logger.info("after warp: %s", _snap(emu))

            prev = _snap(emu)
            for i in range(200):
                cur = _snap(emu)
                active = bool(cur["script_flags"] & SCRIPT_FLAG_SCRIPT_RUNNING)
                if cur["script_mode"] == 1 and active and not cur["joypad_disable"]:
                    emu.press_button("a", hold_frames=8)
                    emu.tick(45)
                    cur = _snap(emu)
                else:
                    emu.tick(30)
                if cur != prev:
                    logger.info("tick %3d: %s", i, cur)
                    prev = cur
                if cur["mom_flag"]:
                    logger.info("Mom scene complete at tick %d", i)
                    break
                if cur["map"] == "24:4":
                    logger.info("Left house at tick %d", i)
                    return 0

            # Navigate to front door after Mom scene
            from src.state.gold_state_reader import PLAYERS_HOUSE_1F_DOOR

            for _ in range(80):
                gs = emu.get_game_state()
                if gs.map_key == "24:4":
                    logger.info("Left house: %s", _snap(emu))
                    return 0
                path = find_path(
                    gs.player.x,
                    gs.player.y,
                    PLAYERS_HOUSE_1F_DOOR[0],
                    PLAYERS_HOUSE_1F_DOOR[1],
                    map_key="24:6",
                )
                if path:
                    emu.press_button(path[0], hold_frames=12)
                emu.tick(30)
                cur = _snap(emu)
                if cur["map"] == "24:4":
                    logger.info("Left house via door: %s", cur)
                    return 0

            logger.info("final: %s", _snap(emu))
            pos = _snap(emu)["pos"]
            if pos == MOM_SCENE_ENTRY_POS and not _snap(emu)["mom_flag"]:
                logger.warning("STUCK at Mom entry position")
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())