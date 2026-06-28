"""Shared test fixtures."""

from __future__ import annotations

import pytest

from src.tools import pokemon_tools
from src.state.gold_state_reader import (
    ADDR_BATTLE_MODE,
    ADDR_ENEMY_HP,
    ADDR_ENEMY_MAX_HP,
    ADDR_ENEMY_SPECIES,
    ADDR_JOHTO_BADGES,
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_MONEY,
    ADDR_NUM_ITEMS,
    ADDR_ITEMS,
    ADDR_PARTY_COUNT,
    ADDR_PARTY_MON1,
    ADDR_PARTY_SPECIES,
    ADDR_X_COORD,
    ADDR_Y_COORD,
    ByteArrayReader,
    GoldStateReader,
    PARTYMON_HP_OFFSET,
    PARTYMON_LEVEL_OFFSET,
)


@pytest.fixture(autouse=True)
def _clear_llm_api_keys(monkeypatch):
    """Prevent real API keys in the environment from affecting heuristic tests."""
    for key in ("XAI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _reset_emulator_binding():
    pokemon_tools.unbind_emulator()
    yield
    pokemon_tools.unbind_emulator()


@pytest.fixture
def new_bark_ram() -> dict[int, int]:
    """Synthetic RAM snapshot: player in New Bark Town with starter."""
    mem: dict[int, int] = {}
    mem[ADDR_MAP_GROUP] = 0
    mem[ADDR_MAP_NUMBER] = 0
    mem[ADDR_X_COORD] = 8
    mem[ADDR_Y_COORD] = 12
    mem[ADDR_MONEY] = 0x00
    mem[ADDR_MONEY + 1] = 0x10
    mem[ADDR_MONEY + 2] = 0x00  # 1000 BCD
    mem[ADDR_PARTY_COUNT] = 1
    mem[ADDR_PARTY_SPECIES] = 152  # Chikorita
    base = ADDR_PARTY_MON1
    mem[base + PARTYMON_HP_OFFSET] = 20
    mem[base + PARTYMON_HP_OFFSET + 1] = 0
    mem[base + PARTYMON_HP_OFFSET + 2] = 20
    mem[base + PARTYMON_HP_OFFSET + 3] = 0
    mem[base + PARTYMON_LEVEL_OFFSET] = 5
    mem[ADDR_JOHTO_BADGES] = 0
    mem[ADDR_BATTLE_MODE] = 0
    mem[ADDR_NUM_ITEMS] = 1
    mem[ADDR_ITEMS] = 5  # Poke Ball
    mem[ADDR_ITEMS + 1] = 5
    return mem


@pytest.fixture
def battle_ram(new_bark_ram: dict[int, int]) -> dict[int, int]:
    mem = dict(new_bark_ram)
    mem[ADDR_MAP_GROUP] = 1
    mem[ADDR_MAP_NUMBER] = 1
    mem[ADDR_BATTLE_MODE] = 1
    mem[ADDR_ENEMY_SPECIES] = 161  # Sentret
    mem[ADDR_ENEMY_HP] = 15
    mem[ADDR_ENEMY_HP + 1] = 0
    mem[ADDR_ENEMY_MAX_HP] = 20
    mem[ADDR_ENEMY_MAX_HP + 1] = 0
    return mem


@pytest.fixture
def gold_reader(new_bark_ram: dict[int, int]) -> GoldStateReader:
    return GoldStateReader(ByteArrayReader(new_bark_ram))