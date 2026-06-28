"""Event flag base/index tests (pret/pokegold, verified on live Silver)."""

from __future__ import annotations

from src.state.gold_state_reader import ADDR_EVENT_FLAGS, ADDR_JOYPAD_DISABLE, has_event_flag
from src.state.script_constants import (
    EVENT_EARLS_ACADEMY_EARL,
    EVENT_INITIALIZED_EVENTS,
    EVENT_PLAYERS_HOUSE_MOM_1,
    EVENT_PLAYERS_HOUSE_MOM_2,
)


def test_event_flag_indices_match_pret_layout():
    assert EVENT_INITIALIZED_EVENTS == 53
    assert EVENT_PLAYERS_HOUSE_MOM_1 == 1735
    assert EVENT_PLAYERS_HOUSE_MOM_2 == 1736
    assert EVENT_EARLS_ACADEMY_EARL == 1739
    assert ADDR_JOYPAD_DISABLE - ADDR_EVENT_FLAGS == 0x103


def test_has_event_flag_round_trip():
    mem: dict[int, int] = {}
    for idx in (EVENT_INITIALIZED_EVENTS, EVENT_PLAYERS_HOUSE_MOM_1):
        byte_addr = ADDR_EVENT_FLAGS + (idx // 8)
        bit = idx % 8
        mem[byte_addr] = mem.get(byte_addr, 0) | (1 << bit)

    class Reader:
        def read_byte(self, address: int) -> int:
            return mem.get(address, 0)

    reader = Reader()
    assert has_event_flag(reader, EVENT_INITIALIZED_EVENTS) is True
    assert has_event_flag(reader, EVENT_PLAYERS_HOUSE_MOM_1) is True
    assert has_event_flag(reader, EVENT_PLAYERS_HOUSE_MOM_2) is False