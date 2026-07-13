"""Minimal emulator that mutates RAM coords — exercises full graph apply_action path."""

from __future__ import annotations

from src.state.gold_state_reader import (
    MAP_CHERRYGROVE_CITY,
    MAP_ROUTE_31,
    MAP_VIOLET_CITY,
    MAP_VIOLET_GYM,
    MAPGROUP_CHERRYGROVE,
    MAPGROUP_VIOLET,
    ADDR_BATTLE_MODE,
    ADDR_ENEMY_HP,
    ADDR_ENEMY_MAX_HP,
    ADDR_ENEMY_SPECIES,
    ADDR_EVENT_FLAGS,
    ADDR_FACING,
    ADDR_JOYPAD_DISABLE,
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_PARTY_COUNT,
    ADDR_PARTY_MON1,
    ADDR_PARTY_SPECIES,
    ADDR_SCRIPT_FLAGS,
    ADDR_SCRIPT_MODE,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    MAP_ELMS_LAB,
    MAP_MR_POKEMONS_HOUSE,
    MAP_NEW_BARK_TOWN,
    MAP_ROUTE_29,
    MAP_ROUTE_30,
    MAPGROUP_JOHTO_ROUTES,
    MAPGROUP_NEW_BARK,
    ByteArrayReader,
    GoldStateReader,
    PARTYMON_HP_OFFSET,
    PARTYMON_LEVEL_OFFSET,
)
from src.state.models import GameState
from src.state.script_constants import (
    EVENT_GAVE_MYSTERY_EGG_TO_ELM,
    EVENT_GOT_A_POKEMON_FROM_ELM,
    EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON,
    JOYPAD_DISABLE_INPUT_MASK,
    SCRIPT_FLAG_SCRIPT_RUNNING,
    SCRIPT_READ,
)


def _set_flag(memory: dict[int, int], flag_index: int) -> None:
    byte_addr = ADDR_EVENT_FLAGS + (flag_index // 8)
    bit = flag_index % 8
    memory[byte_addr] = memory.get(byte_addr, 0) | (1 << bit)


def _has_flag(memory: dict[int, int], flag_index: int) -> bool:
    byte_addr = ADDR_EVENT_FLAGS + (flag_index // 8)
    bit = flag_index % 8
    return bool(memory.get(byte_addr, 0) & (1 << bit))


class MutableRamEmulator:
    """Fake PyBoy wrapper backed by mutable RAM bytes."""

    def __init__(
        self,
        memory: dict[int, int],
        *,
        route_29_west_at_x: int = 0,
        route_29_west_row: int = 8,
    ):
        self._memory = dict(memory)
        self._frame_count = 0
        # Route 29 connects on the west edge of New Bark (pret). Use -1 to disable.
        self._route_29_west_at_x = route_29_west_at_x
        self._route_29_west_row = route_29_west_row

    def press_button(self, button: str, *, hold_frames: int = 2) -> None:
        x = self._memory.get(ADDR_X_COORD, 0)
        y = self._memory.get(ADDR_Y_COORD, 0)
        if button == "right":
            x += 1
        elif button == "left":
            x -= 1
        elif button == "down":
            y += 1
        elif button == "up":
            y -= 1
        self._memory[ADDR_X_COORD] = max(0, x)
        self._memory[ADDR_Y_COORD] = max(0, y)
        self._apply_post_rival_warps()
        self._frame_count += hold_frames + 1

    def _apply_post_rival_warps(self) -> None:
        group = self._memory.get(ADDR_MAP_GROUP, 0)
        map_id = self._memory.get(ADDR_MAP_NUMBER, 0)
        x = self._memory.get(ADDR_X_COORD, 0)
        y = self._memory.get(ADDR_Y_COORD, 0)
        if (
            self._route_29_west_at_x >= 0
            and group == MAPGROUP_NEW_BARK
            and map_id == MAP_NEW_BARK_TOWN
            and y == self._route_29_west_row
            and x <= self._route_29_west_at_x
        ):
            self._memory[ADDR_MAP_GROUP] = MAPGROUP_NEW_BARK
            self._memory[ADDR_MAP_NUMBER] = MAP_ROUTE_29
            self._memory[ADDR_X_COORD] = 10
            self._memory[ADDR_Y_COORD] = 20
            return
        if not _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM):
            return
        # Simplified corridor warps for ROM-free progression tests (not full ROM graph).
        if group == MAPGROUP_NEW_BARK and map_id == MAP_ROUTE_29 and y <= 5:
            self._memory[ADDR_MAP_GROUP] = MAPGROUP_JOHTO_ROUTES
            self._memory[ADDR_MAP_NUMBER] = MAP_ROUTE_30
            self._memory[ADDR_X_COORD] = 10
            self._memory[ADDR_Y_COORD] = 12
            return
        if group == MAPGROUP_JOHTO_ROUTES and map_id == MAP_ROUTE_30 and y <= 3:
            # North of Route 30 → Cherrygrove (simplified; real ROM south is Cherry).
            self._memory[ADDR_MAP_GROUP] = MAPGROUP_CHERRYGROVE
            self._memory[ADDR_MAP_NUMBER] = MAP_CHERRYGROVE_CITY
            self._memory[ADDR_X_COORD] = 17
            self._memory[ADDR_Y_COORD] = 5
            return
        if (
            group == MAPGROUP_CHERRYGROVE
            and map_id == MAP_CHERRYGROVE_CITY
            and y <= 0
        ):
            self._memory[ADDR_MAP_GROUP] = MAPGROUP_JOHTO_ROUTES
            self._memory[ADDR_MAP_NUMBER] = MAP_ROUTE_31
            self._memory[ADDR_X_COORD] = 15
            self._memory[ADDR_Y_COORD] = 8
            return
        if group == MAPGROUP_JOHTO_ROUTES and map_id == MAP_ROUTE_31 and x <= 0:
            self._memory[ADDR_MAP_GROUP] = MAPGROUP_VIOLET
            self._memory[ADDR_MAP_NUMBER] = MAP_VIOLET_CITY
            self._memory[ADDR_X_COORD] = 10
            self._memory[ADDR_Y_COORD] = 17
            return
        if (
            group == MAPGROUP_VIOLET
            and map_id == MAP_VIOLET_CITY
            and x >= 18
            and y >= 17
        ):
            self._memory[ADDR_MAP_GROUP] = MAPGROUP_VIOLET
            self._memory[ADDR_MAP_NUMBER] = MAP_VIOLET_GYM
            self._memory[ADDR_X_COORD] = 4
            self._memory[ADDR_Y_COORD] = 7

    def advance_frames(self, n: int = 1) -> int:
        self._frame_count += n
        return self._frame_count

    def tick(self, frames: int = 1) -> int:
        return self.advance_frames(frames)

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def get_game_state(self) -> GameState:
        return GoldStateReader(
            ByteArrayReader(self._memory), frame_count=self._frame_count
        ).read()


_BUTTON_TO_FACING = {"down": 0, "up": 4, "left": 8, "right": 12}
_ELM_LAB_ALWAYS_BLOCKED = {(5, 2), (6, 3), (7, 3), (8, 3)}
_ELM_LAB_PRE_STARTER_BLOCKED: set[tuple[int, int]] = set()


class PostRivalEmulator(MutableRamEmulator):
    """Post-rival RAM emulator: Route 29/30/Cherrygrove warps when starter flag is set."""


class StarterQuestEmulator(MutableRamEmulator):
    """Quest-aware RAM emulator: warps and flag progression for starter-quest integration."""

    def __init__(self, memory: dict[int, int]):
        super().__init__(memory)
        self._last_button: str | None = None
        self._elm_intro_done = False
        self._desk_script_pending = False

    def _clamp_coords(self, x: int, y: int) -> tuple[int, int]:
        from src.graph.pathfinding import MAP_GRIDS

        group = self._memory.get(ADDR_MAP_GROUP, 0)
        map_id = self._memory.get(ADDR_MAP_NUMBER, 0)
        grid = MAP_GRIDS.get(f"{group}:{map_id}")
        if grid:
            max_x = len(grid[0]) - 1
            max_y = len(grid) - 1
            return max(0, min(x, max_x)), max(0, min(y, max_y))
        return max(0, x), max(0, y)

    def _elm_lab_blocked(self, x: int, y: int) -> bool:
        group = self._memory.get(ADDR_MAP_GROUP, 0)
        map_id = self._memory.get(ADDR_MAP_NUMBER, 0)
        if group != MAPGROUP_NEW_BARK or map_id != MAP_ELMS_LAB:
            return False
        if (x, y) in _ELM_LAB_ALWAYS_BLOCKED:
            return True
        if (x, y) in _ELM_LAB_PRE_STARTER_BLOCKED:
            return not _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
        return False

    def _set_script_active(self) -> None:
        self._memory[ADDR_SCRIPT_FLAGS] = SCRIPT_FLAG_SCRIPT_RUNNING
        self._memory[ADDR_SCRIPT_MODE] = SCRIPT_READ

    def _clear_script(self) -> None:
        self._memory[ADDR_SCRIPT_FLAGS] = 0
        self._memory[ADDR_SCRIPT_MODE] = 0

    def _sync_interact_signals(self) -> None:
        """Emit ROM interact signals when facing quest objects (generic interact policy)."""
        if self._desk_script_pending:
            self._set_script_active()
            return

        group = self._memory.get(ADDR_MAP_GROUP, 0)
        map_id = self._memory.get(ADDR_MAP_NUMBER, 0)
        x = self._memory.get(ADDR_X_COORD, 0)
        y = self._memory.get(ADDR_Y_COORD, 0)

        if group == MAPGROUP_NEW_BARK and map_id == MAP_ELMS_LAB:
            if (x, y) in ((4, 2), (5, 2), (4, 3)) and not self._elm_intro_done:
                self._memory[ADDR_JOYPAD_DISABLE] = JOYPAD_DISABLE_INPUT_MASK
                self._set_script_active()
                return
            ball_tiles = {(6, 3), (7, 3), (8, 3)}
            near_ball = (x, y) in ball_tiles or any(
                abs(x - bx) + abs(y - by) == 1 for bx, by in ball_tiles
            )
            if (
                near_ball
                and self._elm_intro_done
                and not _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
            ):
                self._memory[ADDR_JOYPAD_DISABLE] = JOYPAD_DISABLE_INPUT_MASK
                self._set_script_active()
                return

        if group == MAPGROUP_JOHTO_ROUTES and map_id == MAP_MR_POKEMONS_HOUSE:
            if (x, y) == (5, 5) and not _has_flag(
                self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON
            ):
                self._memory[ADDR_JOYPAD_DISABLE] = JOYPAD_DISABLE_INPUT_MASK
                self._set_script_active()
                return

        self._memory[ADDR_JOYPAD_DISABLE] = 0
        self._clear_script()

    def press_button(self, button: str, *, hold_frames: int = 2) -> None:
        self._last_button = button
        if self._desk_script_pending:
            self._clear_script()
            self._desk_script_pending = False
        x = self._memory.get(ADDR_X_COORD, 0)
        y = self._memory.get(ADDR_Y_COORD, 0)

        if button in ("right", "left", "down", "up"):
            if button == "right":
                x += 1
            elif button == "left":
                x -= 1
            elif button == "down":
                y += 1
            elif button == "up":
                y -= 1
            if self._elm_lab_blocked(x, y):
                self._memory[ADDR_FACING] = _BUTTON_TO_FACING[button]
            else:
                x, y = self._clamp_coords(x, y)
                self._memory[ADDR_X_COORD] = x
                self._memory[ADDR_Y_COORD] = y
                self._memory[ADDR_FACING] = _BUTTON_TO_FACING[button]
            self._apply_warps()
        elif button == "a":
            self._apply_interact()

        self._sync_interact_signals()
        self._frame_count += hold_frames + 1

    def get_game_state(self) -> GameState:
        self._sync_interact_signals()
        return super().get_game_state()

    def _apply_warps(self) -> None:
        group = self._memory.get(ADDR_MAP_GROUP, 0)
        map_id = self._memory.get(ADDR_MAP_NUMBER, 0)
        x = self._memory.get(ADDR_X_COORD, 0)
        y = self._memory.get(ADDR_Y_COORD, 0)

        if group == MAPGROUP_NEW_BARK and map_id == MAP_NEW_BARK_TOWN:
            if y <= 3 and x >= 6:
                self._warp(MAPGROUP_NEW_BARK, MAP_ELMS_LAB, 4, 8)
            elif (
                _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
                and y == self._route_29_west_row
                and x <= self._route_29_west_at_x
            ):
                self._warp(MAPGROUP_NEW_BARK, MAP_ROUTE_29, 10, 12)
            return

        if group == MAPGROUP_NEW_BARK and map_id == MAP_ELMS_LAB:
            if y >= 11 and x in (4, 5):
                self._warp(MAPGROUP_NEW_BARK, MAP_NEW_BARK_TOWN, 13, 6)
            return

        if group == MAPGROUP_NEW_BARK and map_id == MAP_ROUTE_29:
            if _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON) and x <= 1:
                self._warp(MAPGROUP_NEW_BARK, MAP_NEW_BARK_TOWN, 13, 6)
            elif (
                _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
                and not _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)
                and y <= 5
            ):
                self._warp(MAPGROUP_JOHTO_ROUTES, MAP_ROUTE_30, 10, 12)
            return

        if group == MAPGROUP_JOHTO_ROUTES and map_id == MAP_ROUTE_30:
            if _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON) and y >= 12:
                self._warp(MAPGROUP_NEW_BARK, MAP_ROUTE_29, 10, 8)
            elif (
                _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
                and not _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)
                and y <= 3
            ):
                self._warp(MAPGROUP_JOHTO_ROUTES, MAP_MR_POKEMONS_HOUSE, 5, 7)
            return

        if group == MAPGROUP_JOHTO_ROUTES and map_id == MAP_MR_POKEMONS_HOUSE:
            if _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON) and y >= 8:
                self._warp(MAPGROUP_JOHTO_ROUTES, MAP_ROUTE_30, 10, 5)

    def _warp(self, group: int, map_id: int, x: int, y: int) -> None:
        self._memory[ADDR_MAP_GROUP] = group
        self._memory[ADDR_MAP_NUMBER] = map_id
        self._memory[ADDR_X_COORD] = x
        self._memory[ADDR_Y_COORD] = y

    def _apply_interact(self) -> None:
        group = self._memory.get(ADDR_MAP_GROUP, 0)
        map_id = self._memory.get(ADDR_MAP_NUMBER, 0)
        x = self._memory.get(ADDR_X_COORD, 0)
        y = self._memory.get(ADDR_Y_COORD, 0)

        if group == MAPGROUP_NEW_BARK and map_id == MAP_ELMS_LAB:
            if (x, y) in ((4, 2), (5, 2), (4, 3)) and not self._elm_intro_done:
                self._elm_intro_done = True
                self._set_script_active()
                self._desk_script_pending = True
            ball_tiles = {(6, 3), (7, 3), (8, 3)}
            near_ball = (x, y) in ball_tiles or any(
                abs(x - bx) + abs(y - by) == 1 for bx, by in ball_tiles
            )
            if (
                near_ball
                and self._elm_intro_done
                and not _has_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
            ):
                _set_flag(self._memory, EVENT_GOT_A_POKEMON_FROM_ELM)
                self._memory[ADDR_PARTY_COUNT] = 1
                self._memory[ADDR_PARTY_SPECIES] = 158  # Totodile
                base = ADDR_PARTY_MON1
                self._memory[base + PARTYMON_HP_OFFSET] = 20
                self._memory[base + PARTYMON_HP_OFFSET + 1] = 0
                self._memory[base + PARTYMON_HP_OFFSET + 2] = 20
                self._memory[base + PARTYMON_HP_OFFSET + 3] = 0
                self._memory[base + PARTYMON_LEVEL_OFFSET] = 5
            elif (
                (x, y) in ((4, 2), (5, 2))
                and _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)
                and not _has_flag(self._memory, EVENT_GAVE_MYSTERY_EGG_TO_ELM)
            ):
                _set_flag(self._memory, EVENT_GAVE_MYSTERY_EGG_TO_ELM)
            elif (
                _has_flag(self._memory, EVENT_GAVE_MYSTERY_EGG_TO_ELM)
                and self._memory.get(ADDR_BATTLE_MODE, 0) == 0
            ):
                self._memory[ADDR_BATTLE_MODE] = 2
                self._memory[ADDR_ENEMY_SPECIES] = 155  # Cyndaquil (rival)
                self._memory[ADDR_ENEMY_HP] = 18
                self._memory[ADDR_ENEMY_HP + 1] = 0
                self._memory[ADDR_ENEMY_MAX_HP] = 20
                self._memory[ADDR_ENEMY_MAX_HP + 1] = 0
            return

        if group == MAPGROUP_JOHTO_ROUTES and map_id == MAP_MR_POKEMONS_HOUSE:
            if (x, y) == (5, 5) and not _has_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON):
                _set_flag(self._memory, EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)