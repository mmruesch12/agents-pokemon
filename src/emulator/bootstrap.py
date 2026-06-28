"""Boot intro / title / new-game flow until overworld movement works."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from src.state.gold_state_reader import ADDR_MAP_GROUP, ADDR_MAP_NUMBER
from src.state.models import GameState

if TYPE_CHECKING:
    from src.emulator.pyboy_wrapper import PyBoyWrapper

logger = logging.getLogger(__name__)

TITLE_WAIT_FRAMES = int(os.getenv("BOOT_TITLE_WAIT_FRAMES", "3000"))
BOOTSTRAP_MAX_ACTIONS = int(os.getenv("BOOTSTRAP_MAX_ACTIONS", "700"))
MIN_GRAPH_BOOTSTRAP_ACTIONS = int(os.getenv("MIN_GRAPH_BOOTSTRAP_ACTIONS", "15"))
INDOOR_BOOTSTRAP_ACTIONS = int(os.getenv("INDOOR_BOOTSTRAP_ACTIONS", "80"))
MOVEMENT_PROBE_ADDR = 0xC007
MAP_GROUP_ADDR = ADDR_MAP_GROUP
MAP_NUMBER_ADDR = ADDR_MAP_NUMBER
PLAYERS_HOUSE_2F = (3, 4)


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
    if hasattr(emu, "_pyboy"):
        return int(emu._pyboy.memory[address])
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


def in_loaded_map(emu: PyBoyWrapper) -> bool:
    """True once the game has left the title/menu and loaded a map."""
    return read_loaded_map(emu) != (0, 0)


def movement_responsive(emu: PyBoyWrapper, *, probe_button: str = "down") -> bool:
    """Return True when a direction press changes movement-related WRAM on a loaded map."""
    if not in_loaded_map(emu):
        return False

    before = read_memory_byte(emu, MOVEMENT_PROBE_ADDR)
    emu.press_button(probe_button, hold_frames=8)  # type: ignore[arg-type]
    emu.tick(45)
    after = read_memory_byte(emu, MOVEMENT_PROBE_ADDR)
    if before != after:
        return True

    snap = {addr: read_memory_byte(emu, addr) for addr in range(0xC000, 0xC020)}
    emu.press_button(probe_button, hold_frames=8)  # type: ignore[arg-type]
    emu.tick(45)
    return any(read_memory_byte(emu, addr) != snap[addr] for addr in snap)


def is_bootstrap_done(emu: PyBoyWrapper, gs: GameState, state: dict) -> bool:
    """True when intro/title/indoor dialog input can hand off to navigation."""
    idx = state.get("bootstrap_action_index", 0)
    if idx < MIN_GRAPH_BOOTSTRAP_ACTIONS:
        return False
    if gs.party_count > 0:
        return True
    if not in_loaded_map(emu):
        return False

    loaded_map = read_loaded_map(emu)
    if loaded_map == PLAYERS_HOUSE_2F and idx < INDOOR_BOOTSTRAP_ACTIONS:
        return False
    if gs.party_count == 0 and loaded_map == (0, 0):
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
        return True

    return state.get("phase") == "bootstrap"


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


def run_bootstrap(
    emu: PyBoyWrapper,
    *,
    max_actions: int | None = None,
    title_wait_frames: int | None = None,
) -> BootstrapResult:
    """Advance from cold boot through title and new-game setup."""
    max_actions = BOOTSTRAP_MAX_ACTIONS if max_actions is None else max_actions
    title_wait = TITLE_WAIT_FRAMES if title_wait_frames is None else title_wait_frames
    start_frames = emu.frame_count

    gs = emu.get_game_state()
    if not needs_bootstrap(gs, {"bootstrap_complete": False}):
        map_loaded = in_loaded_map(emu)
        return BootstrapResult(
            success=map_loaded,
            movement_ready=False,
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
    emu.press_button("a", hold_frames=12)
    emu.tick(120)

    actions = 2
    for i in range(max_actions):
        if in_loaded_map(emu):
            logger.info(
                "Bootstrap map loaded after %d actions (map=%s)",
                actions,
                read_loaded_map(emu),
            )
            return BootstrapResult(
                success=True,
                movement_ready=False,
                map_loaded=True,
                actions_taken=actions,
                frames_elapsed=emu.frame_count - start_frames,
            )

        button = pick_bootstrap_button(i)
        emu.press_button(button, hold_frames=8)  # type: ignore[arg-type]
        emu.tick(30)
        actions += 1

    map_loaded = in_loaded_map(emu)
    logger.warning(
        "Bootstrap finished without loaded map (actions=%d, map_loaded=%s)",
        actions,
        map_loaded,
    )
    return BootstrapResult(
        success=map_loaded,
        movement_ready=False,
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