"""Boot intro / title / new-game flow until overworld movement works."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from src.state.gold_state_reader import (
    ADDR_EVENT_FLAGS,
    ADDR_FACING,
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_PARTY_COUNT,
    ADDR_PARTY_SPECIES,
    ADDR_SCRIPT_FLAGS,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    EVENT_INITIALIZED_EVENTS,
    MAP_KEY_ELMS_LAB,
    MAP_PLAYERS_HOUSE_2F,
    MAPGROUP_NEW_BARK,
    coords_playable,
    has_event_flag,
)
from src.state.script_constants import (
    EVENT_GOT_A_POKEMON_FROM_ELM,
    EVENT_GOT_CHIKORITA_FROM_ELM,
    EVENT_GOT_CYNDAQUIL_FROM_ELM,
    EVENT_GOT_TOTODILE_FROM_ELM,
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


BEDROOM_START_STATE = os.getenv("BEDROOM_START_STATE", "bedroom_start")
LAB_DESK_START_STATE = os.getenv("LAB_DESK_START_STATE", "lab_desk_start")


def seed_bedroom_agent_state(
    state: dict,
    gs: GameState,
    *,
    bootstrap_actions: int = 0,
) -> dict:
    """Seed agent state for house-exit gameplay from Player's House 2F."""
    from src.graph.state import update_game_state
    from src.state.gold_state_reader import MAP_KEY_PLAYERS_HOUSE_2F

    result = BootstrapResult(
        success=True,
        movement_ready=True,
        map_loaded=True,
        actions_taken=bootstrap_actions,
        frames_elapsed=0,
    )
    gs = apply_bootstrap_metadata(gs, result)
    state = update_game_state(state, gs)
    state["bootstrap_complete"] = True
    state["phase"] = "explore"
    state["bootstrap_action_index"] = INDOOR_BOOTSTRAP_ACTIONS
    state["movement_observed"] = True
    maps = list(state.get("maps_visited", []))
    if MAP_KEY_PLAYERS_HOUSE_2F not in maps:
        maps.append(MAP_KEY_PLAYERS_HOUSE_2F)
    state["maps_visited"] = maps
    state["active_subgoal"] = "Leave player house"
    state["house_exit_complete"] = False
    state["starter_quest_complete"] = False
    return state


def prepare_bedroom_start(
    emu: PyBoyWrapper,
    state: dict,
    *,
    rom_path: str | Path | None = None,
    save_dir: str | Path | None = None,
    bedroom_state_name: str | None = None,
) -> dict:
    """Fast-start emulator in Player's House 2F; skip graph intro/bootstrap."""
    from src.state.gold_state_reader import MAP_KEY_PLAYERS_HOUSE_2F

    save_dir = Path(save_dir or "saves")
    bedroom_state_name = bedroom_state_name or BEDROOM_START_STATE
    cache_path = save_dir / f"{bedroom_state_name}.state"

    if cache_path.is_file():
        emu.load_state(bedroom_state_name)
        gs = emu.get_game_state()
        if gs.map_key == MAP_KEY_PLAYERS_HOUSE_2F:
            logger.info("Loaded cached bedroom start from %s", cache_path.name)
            return seed_bedroom_agent_state(state, gs)
        logger.warning(
            "Cached bedroom save invalid (map=%s); removing and re-bootstrapping",
            gs.map_key,
        )
        try:
            cache_path.unlink()
        except Exception:
            pass

    logger.info("Bedroom start: running emulator bootstrap to Player's House 2F")
    result = run_bootstrap(emu, rom_path=rom_path)
    wait_for_init_events(emu)
    gs = emu.get_game_state()
    loaded_map = read_loaded_map(emu)
    if loaded_map != PLAYERS_HOUSE_2F:
        raise RuntimeError(
            "Bedroom start failed: expected Player's House 2F "
            f"(map={loaded_map}), bootstrap movement_ready={result.movement_ready}"
        )
    if not result.movement_ready and not movement_responsive(emu):
        raise RuntimeError(
            "Bedroom start failed: player cannot move in bedroom after bootstrap"
        )

    gs = apply_bootstrap_metadata(
        gs,
        BootstrapResult(
            success=True,
            movement_ready=True,
            map_loaded=True,
            actions_taken=result.actions_taken,
            frames_elapsed=result.frames_elapsed,
        ),
    )
    try:
        emu.save_state(bedroom_state_name)
        logger.info("Cached bedroom start as %s.state", bedroom_state_name)
    except OSError as exc:
        logger.warning("Could not cache bedroom start: %s", exc)

    return seed_bedroom_agent_state(state, gs, bootstrap_actions=result.actions_taken)


def _clear_event_flag(emu: PyBoyWrapper, flag_index: int) -> None:
    byte_addr = ADDR_EVENT_FLAGS + (flag_index // 8)
    bit = flag_index % 8
    current = emu.read_byte(byte_addr)
    emu.write_byte(byte_addr, current & ~(1 << bit))


def _at_elm_desk(gs: GameState) -> bool:
    return (gs.player.x, gs.player.y) in ((4, 2), (5, 2), (4, 3))


def _desk_dialog_done_for_seed(gs: GameState) -> bool:
    if (gs.player.x, gs.player.y) in ((5, 3), (6, 3), (7, 3), (8, 3)):
        return True
    return gs.player.y >= 3 and not _at_elm_desk(gs)


def repair_elms_lab_snapshot(emu: PyBoyWrapper, gs: GameState) -> GameState:
    """Fix fast-start saves: starter flag without party, invalid facing byte."""
    from src.graph.phases import starter_quest

    if gs.map_key != MAP_KEY_ELMS_LAB:
        return gs

    meta = gs.raw_metadata or {}
    if gs.party_count == 0 and meta.get("has_starter"):
        for flag in (
            EVENT_GOT_A_POKEMON_FROM_ELM,
            EVENT_GOT_CYNDAQUIL_FROM_ELM,
            EVENT_GOT_TOTODILE_FROM_ELM,
            EVENT_GOT_CHIKORITA_FROM_ELM,
        ):
            _clear_event_flag(emu, flag)
        emu.write_byte(ADDR_PARTY_COUNT, 0)
        emu.write_byte(ADDR_PARTY_SPECIES, 0)
        logger.info("Cleared desynced Elm starter flag (party empty)")
        gs = emu.get_game_state()
    elif not meta.get("has_starter") and _at_elm_desk(gs):
        if emu.read_byte(ADDR_PARTY_COUNT) == 0 and emu.read_byte(ADDR_PARTY_SPECIES) != 0:
            emu.write_byte(ADDR_PARTY_SPECIES, 0)
            logger.info("Cleared stale party species byte at Elm desk (count=0)")
            gs = emu.get_game_state()

    if _at_elm_desk(gs) and not starter_quest.has_starter(gs):
        if gs.player.facing != 4:
            emu.write_byte(ADDR_FACING, 4)
            logger.info(
                "Aligned desk facing %s -> 4 (up) at (%d,%d)",
                gs.player.facing,
                gs.player.x,
                gs.player.y,
            )
    elif gs.player.facing not in (0, 4, 8, 12):
        emu.write_byte(ADDR_FACING, 12)
        logger.info("Normalized invalid facing %s -> 12", gs.player.facing)

    return emu.get_game_state()


def seed_lab_agent_state(
    state: dict,
    gs: GameState,
    *,
    reset_lab_counters: bool = True,
) -> dict:
    """Seed agent state for starter-quest gameplay from an Elm's Lab emulator snapshot."""
    from src.graph.state import update_game_state
    from src.graph.phases import starter_quest
    from src.graph.phases.house_exit import HOUSE_EXIT_MILESTONE
    from src.state.gold_state_reader import (
        MAP_KEY_ELMS_LAB,
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_PLAYERS_HOUSE_1F,
        MAP_KEY_PLAYERS_HOUSE_2F,
    )

    result = BootstrapResult(
        success=True,
        movement_ready=True,
        map_loaded=True,
        actions_taken=INDOOR_BOOTSTRAP_ACTIONS,
        frames_elapsed=0,
    )
    gs = apply_bootstrap_metadata(gs, result)
    state = update_game_state(state, gs)
    state["bootstrap_complete"] = True
    state["phase"] = "explore"
    state["bootstrap_action_index"] = INDOOR_BOOTSTRAP_ACTIONS
    state["movement_observed"] = True
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = False
    state["should_replan"] = False
    state["stuck_count"] = 0
    state["maps_visited"] = [
        MAP_KEY_PLAYERS_HOUSE_2F,
        MAP_KEY_PLAYERS_HOUSE_1F,
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ELMS_LAB,
    ]
    milestones = list(state.get("milestones", []))
    for milestone in (
        "Reached Player's House 1F",
        HOUSE_EXIT_MILESTONE,
        starter_quest.MILESTONE_ENTERED_LAB,
    ):
        if milestone not in milestones:
            milestones.append(milestone)
    state["milestones"] = milestones
    if reset_lab_counters:
        state["lab_desk_dialog_done"] = _desk_dialog_done_for_seed(gs)
        state["lab_desk_interact_count"] = 0
        state["lab_desk_script_seen"] = False
        state["lab_steps_without_party"] = 0
        state["lab_stall_position"] = None
        state["short_term_history"] = []
        state["should_replan"] = False
        state["replan_count"] = 0
    from src.memory.landmarks import discover_elms_lab_landmarks

    state["known_landmarks"] = discover_elms_lab_landmarks(gs)
    starter_quest.sync_subgoals(gs, state)
    return state


def seed_agent_state_for_map(state: dict, gs: GameState) -> dict:
    """Infer graph flags from the map loaded in a PyBoy .state snapshot."""
    from src.graph.state import update_game_state
    from src.state.gold_state_reader import (
        MAP_KEY_ELMS_LAB,
        MAP_KEY_PLAYERS_HOUSE_2F,
    )

    if gs.map_key == MAP_KEY_PLAYERS_HOUSE_2F:
        return seed_bedroom_agent_state(state, gs)
    if gs.map_key == MAP_KEY_ELMS_LAB:
        return seed_lab_agent_state(state, gs)
    result = BootstrapResult(
        success=True,
        movement_ready=True,
        map_loaded=True,
        actions_taken=INDOOR_BOOTSTRAP_ACTIONS,
        frames_elapsed=0,
    )
    gs = apply_bootstrap_metadata(gs, result)
    state = update_game_state(state, gs)
    state["bootstrap_complete"] = True
    state["phase"] = "explore"
    state["bootstrap_action_index"] = INDOOR_BOOTSTRAP_ACTIONS
    state["movement_observed"] = True
    return state


def prepare_emulator_state(
    emu: PyBoyWrapper,
    state: dict,
    state_name: str,
    *,
    save_dir: str | Path | None = None,
    expected_map_key: str | None = None,
) -> dict:
    """Load a named PyBoy snapshot from saves/ and seed matching agent state."""
    from src.state.gold_state_reader import MAP_KEY_ELMS_LAB

    save_dir = Path(save_dir or "saves")
    cache_path = save_dir / f"{state_name}.state"
    if not cache_path.is_file():
        raise FileNotFoundError(
            f"Emulator state not found: {cache_path}. "
            "Run a longer session first (saves/stuck_*.state and saves/final_*.state "
            "are written automatically), then install one with "
            "`poke-agent capture-lab-start --from-save <name>`."
        )
    emu.load_state(state_name)
    gs = emu.get_game_state()
    if expected_map_key and gs.map_key != expected_map_key:
        raise RuntimeError(
            f"Emulator state {state_name!r} is on map {gs.map_key}, "
            f"expected {expected_map_key}"
        )
    if gs.map_key == MAP_KEY_ELMS_LAB:
        gs = repair_elms_lab_snapshot(emu, gs)
    logger.info(
        "Loaded emulator state %s (map=%s pos=(%d,%d))",
        cache_path.name,
        gs.map_key,
        gs.player.x,
        gs.player.y,
    )
    if gs.map_key == MAP_KEY_ELMS_LAB:
        return seed_lab_agent_state(state, gs)
    return seed_agent_state_for_map(state, gs)


def prepare_lab_start(
    emu: PyBoyWrapper,
    state: dict,
    *,
    save_dir: str | Path | None = None,
    lab_state_name: str | None = None,
) -> dict:
    """Fast-start at Elm's Lab using saves/lab_desk_start.state (or LAB_DESK_START_STATE)."""
    from src.state.gold_state_reader import MAP_KEY_ELMS_LAB

    return prepare_emulator_state(
        emu,
        state,
        lab_state_name or LAB_DESK_START_STATE,
        save_dir=save_dir,
        expected_map_key=MAP_KEY_ELMS_LAB,
    )


def install_lab_start_from_save(
    source_name: str,
    *,
    target_name: str | None = None,
    save_dir: str | Path | None = None,
) -> Path:
    """Copy an existing snapshot (e.g. final_200 or stuck_198) to lab_desk_start.state."""
    import shutil

    save_dir = Path(save_dir or "saves")
    source_path = save_dir / f"{source_name}.state"
    if not source_path.is_file():
        raise FileNotFoundError(f"Source emulator state not found: {source_path}")
    target_name = target_name or LAB_DESK_START_STATE
    target_path = save_dir / f"{target_name}.state"
    shutil.copy2(source_path, target_path)
    logger.info("Installed %s -> %s", source_path.name, target_path.name)
    return target_path
