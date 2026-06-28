"""Boot intro / title / new-game flow until overworld movement works."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from src.state.gold_state_reader import (
    ADDR_FACING,
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_SCRIPT_FLAGS,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    EVENT_INITIALIZED_EVENTS,
    MAP_PLAYERS_HOUSE_2F,
    MAPGROUP_NEW_BARK,
    coords_playable,
    has_event_flag,
)
from src.state.script_constants import SCRIPT_FLAG_SCRIPT_RUNNING
from src.state.models import GameState

if TYPE_CHECKING:
    from src.emulator.pyboy_wrapper import PyBoyWrapper

logger = logging.getLogger(__name__)

TITLE_WAIT_FRAMES = int(os.getenv("BOOT_TITLE_WAIT_FRAMES", "3000"))
BOOTSTRAP_MAX_ACTIONS = int(os.getenv("BOOTSTRAP_MAX_ACTIONS", "700"))
MIN_GRAPH_BOOTSTRAP_ACTIONS = int(os.getenv("MIN_GRAPH_BOOTSTRAP_ACTIONS", "15"))
INDOOR_BOOTSTRAP_ACTIONS = int(os.getenv("INDOOR_BOOTSTRAP_ACTIONS", "80"))
INIT_EVENTS_WAIT_FRAMES = int(os.getenv("INIT_EVENTS_WAIT_FRAMES", "360"))
MAP_GROUP_ADDR = ADDR_MAP_GROUP
MAP_NUMBER_ADDR = ADDR_MAP_NUMBER
PLAYERS_HOUSE_2F = (MAPGROUP_NEW_BARK, MAP_PLAYERS_HOUSE_2F)


class MemoryReadable(Protocol):
    def read_byte(self, address: int) -> int: ...


@dataclass(frozen=True)
class BootstrapResult:
    success: bool
    movement_ready: bool
    map_loaded: bool
    actions_taken: int
    frames_elapsed: int


def read_memory_byte(emu: PyBoyWrapper, address: int) -> int:
    read_byte = getattr(emu, "read_byte", None)
    if callable(read_byte):
        return int(read_byte(address))
    memory = getattr(emu, "_memory", None)
    if memory is not None:
        return int(memory.get(address, 0))
    raise TypeError(f"Unsupported emulator type for memory read: {type(emu)!r}")


def read_loaded_map(emu: PyBoyWrapper) -> tuple[int, int]:
    """Map group/number from pret wMapGroup / wMapNumber (WRAM bank 1)."""
    return (
        read_memory_byte(emu, MAP_GROUP_ADDR),
        read_memory_byte(emu, MAP_NUMBER_ADDR),
    )


def read_player_coords(emu: PyBoyWrapper) -> tuple[int, int]:
    return (
        read_memory_byte(emu, ADDR_X_COORD),
        read_memory_byte(emu, ADDR_Y_COORD),
    )


def in_loaded_map(emu: PyBoyWrapper) -> bool:
    """True once the game has left the title/menu and loaded a map."""
    return read_loaded_map(emu) != (0, 0)


def movement_responsive(emu: PyBoyWrapper, *, probe_button: str = "down") -> bool:
    """Return True when a direction press changes wXCoord/wYCoord on a loaded map."""
    if not in_loaded_map(emu):
        return False
    x_before, y_before = read_player_coords(emu)
    if not coords_playable(x_before, y_before):
        return False

    for direction in (probe_button, "right", "left", "up", "down"):
        emu.press_button(direction, hold_frames=12)  # type: ignore[arg-type]
        emu.tick(45)
        x_after, y_after = read_player_coords(emu)
        if (x_before, y_before) != (x_after, y_after):
            return True
    return False


def is_bootstrap_done(emu: PyBoyWrapper, gs: GameState, state: dict) -> bool:
    """True when intro/title/indoor dialog input can hand off to navigation."""
    idx = state.get("bootstrap_action_index", 0)
    if idx < MIN_GRAPH_BOOTSTRAP_ACTIONS:
        return False
    if gs.party_count > 0:
        return True
    if not in_loaded_map(emu):
        return False

    x, y = read_player_coords(emu)
    if not coords_playable(x, y):
        return False
    if not state.get("movement_observed") and not movement_responsive(emu):
        return False

    loaded_map = read_loaded_map(emu)
    if loaded_map == PLAYERS_HOUSE_2F and idx < INDOOR_BOOTSTRAP_ACTIONS:
        return False
    if gs.party_count == 0 and loaded_map == (MAPGROUP_NEW_BARK, 0):
        return False
    return True


def needs_bootstrap(
    gs: GameState,
    state: dict | None = None,
    *,
    movement_ready: bool | None = None,
) -> bool:
    """True while the game still needs title/menu/dialog input rather than navigation."""
    state = state or {}
    if state.get("bootstrap_complete"):
        return False

    meta = gs.raw_metadata or {}
    if movement_ready is None:
        movement_ready = bool(meta.get("movement_ready"))
    if movement_ready:
        return False

    if gs.battle.in_battle:
        return False
    if gs.party_count > 0:
        return False

    if gs.player.x == 0 and gs.player.y == 0 and gs.party_count == 0:
        if gs.player.map_group == 0 and gs.player.map_id == 0:
            return True

    return state.get("phase") == "bootstrap"


def map_script_active(emu: PyBoyWrapper) -> bool:
    """True while pret's script engine is executing (wScriptFlags bit 2)."""
    return bool(read_memory_byte(emu, ADDR_SCRIPT_FLAGS) & SCRIPT_FLAG_SCRIPT_RUNNING)


def wait_for_init_events(emu: PyBoyWrapper, *, max_frames: int | None = None) -> bool:
    """Let PlayersHouse2F map callbacks finish without pressing buttons."""
    max_frames = INIT_EVENTS_WAIT_FRAMES if max_frames is None else max_frames
    ticks = 0
    while ticks < max_frames:
        if has_event_flag(_EmuByteReader(emu), EVENT_INITIALIZED_EVENTS):
            return True
        emu.tick(30)
        ticks += 30
    return has_event_flag(_EmuByteReader(emu), EVENT_INITIALIZED_EVENTS)


class _EmuByteReader:
    def __init__(self, emu: PyBoyWrapper):
        self._emu = emu

    def read_byte(self, address: int) -> int:
        return read_memory_byte(self._emu, address)


def pick_bootstrap_button(
    action_index: int,
    *,
    loaded_map: tuple[int, int] | None = None,
) -> str:
    """Heuristic button schedule for title, dialog, name, clock, and indoor maps."""
    if loaded_map == PLAYERS_HOUSE_2F:
        if action_index % 6 == 0:
            return "down"
        if action_index % 11 == 5:
            return "left"
        if action_index % 13 == 7:
            return "right"
        return "a"

    if action_index % 100 == 0:
        return "start"
    if action_index % 45 == 20:
        return "down"
    if action_index % 60 == 30:
        return "right"
    return "a"


def _rom_has_battery_save(rom_path: str | Path) -> bool:
    path = Path(rom_path)
    return path.with_suffix(path.suffix + ".ram").exists()


def run_bootstrap(
    emu: PyBoyWrapper,
    *,
    max_actions: int | None = None,
    title_wait_frames: int | None = None,
    rom_path: str | Path | None = None,
) -> BootstrapResult:
    """Advance from cold boot through title and new-game setup."""
    max_actions = BOOTSTRAP_MAX_ACTIONS if max_actions is None else max_actions
    title_wait = TITLE_WAIT_FRAMES if title_wait_frames is None else title_wait_frames
    start_frames = emu.frame_count

    gs = emu.get_game_state()
    if not needs_bootstrap(gs, {"bootstrap_complete": False}):
        map_loaded = in_loaded_map(emu)
        movement_ready = movement_responsive(emu) if map_loaded else False
        return BootstrapResult(
            success=map_loaded,
            movement_ready=movement_ready,
            map_loaded=map_loaded,
            actions_taken=0,
            frames_elapsed=emu.frame_count - start_frames,
        )

    logger.info("Running bootstrap: waiting %d frames for title screen", title_wait)
    fast_forward = getattr(emu, "fast_forward", None)
    if callable(fast_forward):
        with fast_forward():
            emu.tick(title_wait)
    else:
        emu.tick(title_wait)

    emu.press_button("start", hold_frames=12)
    emu.tick(120)
    rom = rom_path or getattr(emu, "rom_path", None)
    if rom is None:
        rom = getattr(emu, "_rom_path", None)
    if rom is not None and _rom_has_battery_save(rom):
        emu.press_button("down", hold_frames=12)
        emu.tick(120)
    emu.press_button("a", hold_frames=12)
    emu.tick(120)

    actions = 2
    logged_map = False
    for i in range(max_actions):
        loaded_map = read_loaded_map(emu) if in_loaded_map(emu) else None
        if loaded_map and not logged_map:
            logger.info(
                "Bootstrap map loaded after %d actions (map=%s)",
                actions,
                loaded_map,
            )
            logged_map = True
        if loaded_map == PLAYERS_HOUSE_2F and map_script_active(emu):
            emu.tick(30)
            actions += 1
            continue
        if in_loaded_map(emu):
            x, y = read_player_coords(emu)
            if coords_playable(x, y) and movement_responsive(emu):
                logger.info(
                    "Bootstrap movement ready after %d actions (pos=(%d,%d))",
                    actions,
                    x,
                    y,
                )
                return BootstrapResult(
                    success=True,
                    movement_ready=True,
                    map_loaded=True,
                    actions_taken=actions,
                    frames_elapsed=emu.frame_count - start_frames,
                )

        button = pick_bootstrap_button(i, loaded_map=loaded_map)
        emu.press_button(button, hold_frames=8)  # type: ignore[arg-type]
        emu.tick(30)
        actions += 1

    map_loaded = in_loaded_map(emu)
    movement_ready = movement_responsive(emu) if map_loaded else False
    logger.warning(
        "Bootstrap finished (actions=%d, map_loaded=%s, movement_ready=%s)",
        actions,
        map_loaded,
        movement_ready,
    )
    return BootstrapResult(
        success=map_loaded and movement_ready,
        movement_ready=movement_ready,
        map_loaded=map_loaded,
        actions_taken=actions,
        frames_elapsed=emu.frame_count - start_frames,
    )


def apply_bootstrap_metadata(gs: GameState, result: BootstrapResult) -> GameState:
    """Attach bootstrap outcome to game state for graph routing."""
    meta = dict(gs.raw_metadata)
    meta["map_loaded"] = result.map_loaded
    meta["movement_ready"] = result.movement_ready
    meta["bootstrap_actions"] = result.actions_taken
    return gs.model_copy(update={"raw_metadata": meta})