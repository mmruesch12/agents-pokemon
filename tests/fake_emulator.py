"""Minimal emulator that mutates RAM coords — exercises full graph apply_action path."""

from __future__ import annotations

from src.emulator.bootstrap import MOVEMENT_PROBE_ADDR
from src.state.gold_state_reader import (
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    ByteArrayReader,
    GoldStateReader,
)
from src.state.models import GameState


class MutableRamEmulator:
    """Fake PyBoy wrapper backed by mutable RAM bytes."""

    def __init__(self, memory: dict[int, int], *, route_29_at_x: int = 18):
        self._memory = dict(memory)
        self._frame_count = 0
        self._route_29_at_x = route_29_at_x

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
        self._memory[MOVEMENT_PROBE_ADDR] = self._memory.get(MOVEMENT_PROBE_ADDR, 0) + 1
        if (
            self._memory.get(ADDR_MAP_GROUP) == 0
            and self._memory.get(ADDR_MAP_NUMBER) == 0
            and self._memory[ADDR_X_COORD] >= self._route_29_at_x
        ):
            self._memory[ADDR_MAP_GROUP] = 1
            self._memory[ADDR_MAP_NUMBER] = 1
            self._memory[ADDR_X_COORD] = 10
            self._memory[ADDR_Y_COORD] = 20
        self._frame_count += hold_frames + 1

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