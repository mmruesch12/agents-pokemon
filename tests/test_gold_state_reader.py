"""Tests for GoldStateReader RAM parsing."""

from __future__ import annotations

from src.state.gold_state_reader import (
    ADDR_JOHTO_BADGES,
    ByteArrayReader,
    GoldStateReader,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
)


def test_canonical_map_keys_match_pret():
    """New Bark exterior is group 24 map 4 (not boot placeholder 0:0)."""
    from src.state.gold_state_reader import MAP_KEY_UNINITIALIZED

    assert MAP_KEY_NEW_BARK_TOWN == "24:4"
    assert MAP_KEY_PLAYERS_HOUSE_1F == "24:6"
    assert MAP_KEY_PLAYERS_HOUSE_2F == "24:7"
    assert MAP_KEY_UNINITIALIZED == "0:0"


def test_read_player_position(gold_reader: GoldStateReader):
    player = gold_reader.read_player()
    assert player.map_group == 24
    assert player.map_id == 4
    assert player.map_name == "New Bark Town"
    assert player.x == 8
    assert player.y == 12


def test_read_party(gold_reader: GoldStateReader):
    count, party = gold_reader.read_party()
    assert count == 1
    assert len(party) == 1
    assert party[0].species_id == 152
    assert party[0].species_name == "Chikorita"
    assert party[0].level == 5
    assert party[0].hp == 20
    assert party[0].max_hp == 20


def test_read_party_infers_count_when_species_present():
    from src.state.gold_state_reader import (
        ADDR_EVENT_FLAGS,
        ADDR_PARTY_COUNT,
        ADDR_PARTY_MON1,
        ADDR_PARTY_SPECIES,
        PARTYMON_HP_OFFSET,
        PARTYMON_LEVEL_OFFSET,
    )
    from src.state.script_constants import EVENT_GOT_A_POKEMON_FROM_ELM

    flag_addr = ADDR_EVENT_FLAGS + (EVENT_GOT_A_POKEMON_FROM_ELM // 8)
    mem = {
        ADDR_PARTY_COUNT: 0,
        ADDR_PARTY_SPECIES: 158,
        ADDR_PARTY_MON1 + PARTYMON_HP_OFFSET: 0,
        ADDR_PARTY_MON1 + PARTYMON_HP_OFFSET + 1: 20,
        ADDR_PARTY_MON1 + PARTYMON_HP_OFFSET + 2: 0,
        ADDR_PARTY_MON1 + PARTYMON_HP_OFFSET + 3: 20,
        ADDR_PARTY_MON1 + PARTYMON_LEVEL_OFFSET: 5,
        flag_addr: 1 << (EVENT_GOT_A_POKEMON_FROM_ELM % 8),
    }
    reader = GoldStateReader(ByteArrayReader(mem))
    count, party = reader.read_party()
    assert count == 1
    assert party[0].species_id == 158


def test_read_party_does_not_infer_count_without_starter_flag():
    from src.state.gold_state_reader import ADDR_PARTY_COUNT, ADDR_PARTY_SPECIES

    mem = {ADDR_PARTY_COUNT: 0, ADDR_PARTY_SPECIES: 165}
    reader = GoldStateReader(ByteArrayReader(mem))
    count, party = reader.read_party()
    assert count == 0
    assert party == []


def test_read_money_bcd(gold_reader: GoldStateReader):
    player = gold_reader.read_player()
    assert player.money == 1000


def test_read_inventory(gold_reader: GoldStateReader):
    items = gold_reader.read_inventory()
    assert len(items) == 1
    assert items[0].item_id == 5
    assert items[0].quantity == 5


def test_read_badges():
    mem = {ADDR_JOHTO_BADGES: 0b00000011}
    reader = GoldStateReader(ByteArrayReader(mem))
    state = reader.read()
    assert state.johto_badges == 3
    assert "Zephyr" in state.badge_names
    assert "Hive" in state.badge_names
    assert state.total_badges == 2


def test_read_battle_state(battle_ram: dict):
    reader = GoldStateReader(ByteArrayReader(battle_ram))
    battle = reader.read_battle()
    assert battle.in_battle is True
    assert battle.enemy_species_id == 161
    assert battle.enemy_hp == 15
    assert battle.can_run is True


def test_full_game_state(gold_reader: GoldStateReader):
    state = gold_reader.read()
    assert state.party_count == 1
    assert state.battle.in_battle is False
    assert state.map_key == "24:4"
    assert state.position_key == "24:4:8:12"