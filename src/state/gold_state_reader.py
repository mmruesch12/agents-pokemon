"""Gen 2 RAM parsers for Pokemon Gold/Silver (pret/pokegold + Data Crystal)."""

from __future__ import annotations

from typing import Protocol

from src.state.models import (
    BattlePhase,
    BattleState,
    GameState,
    InventoryItem,
    PartyMember,
    PlayerState,
)
from src.state.script_constants import (
    EVENT_INITIALIZED_EVENTS,
    EVENT_PLAYERS_HOUSE_MOM_1,
    SCRIPT_FLAG_SCRIPT_RUNNING,
    SCRIPT_READ,
    SCRIPT_WAIT,
    SCRIPT_WAIT_MOVEMENT,
)

# WRAM addresses from pret/pokegold (wCurMapData in WRAM bank 1).
# Verified against live Silver cold-boot: D087 held map height/width, not group/id.
ADDR_WARP_NUMBER = 0xD9FF  # wWarpNumber
ADDR_MAP_GROUP = 0xDA00  # wMapGroup
ADDR_MAP_NUMBER = 0xDA01  # wMapNumber
ADDR_Y_COORD = 0xDA02  # wYCoord
ADDR_X_COORD = 0xDA03  # wXCoord
ADDR_FACING = 0xD4B7  # wPlayerStruct + OBJECT_DIRECTION

MAPGROUP_NEW_BARK = 24
MAP_NEW_BARK_TOWN = 4
MAP_ROUTE_29 = 3
MAP_PLAYERS_HOUSE_1F = 6
MAP_PLAYERS_HOUSE_2F = 7

# Canonical map_key strings (group:map_id) — pret/pokegold WRAM.
MAP_KEY_NEW_BARK_TOWN = f"{MAPGROUP_NEW_BARK}:{MAP_NEW_BARK_TOWN}"
MAP_KEY_PLAYERS_HOUSE_1F = f"{MAPGROUP_NEW_BARK}:{MAP_PLAYERS_HOUSE_1F}"
MAP_KEY_PLAYERS_HOUSE_2F = f"{MAPGROUP_NEW_BARK}:{MAP_PLAYERS_HOUSE_2F}"
MAP_KEY_ROUTE_29 = f"{MAPGROUP_NEW_BARK}:{MAP_ROUTE_29}"
# Uninitialized map before overworld load (title screen / boot), not New Bark Town.
MAP_KEY_UNINITIALIZED = "0:0"

MAX_PLAYABLE_COORD = 31
INVALID_FACING = 255

ADDR_PARTY_COUNT = 0xD163
ADDR_PARTY_SPECIES = 0xD164
ADDR_PARTY_MON1 = 0xD16B

ADDR_MONEY = 0xD573
ADDR_JOHTO_BADGES = 0xD356
ADDR_KANTO_BADGES = 0xD355

ADDR_BATTLE_MODE = 0xD057
ADDR_ENEMY_SPECIES = 0xD0D0
ADDR_ENEMY_HP = 0xD0CE
ADDR_ENEMY_MAX_HP = 0xD0D8

ADDR_NUM_ITEMS = 0xD89E
ADDR_ITEMS = 0xD89F

ADDR_EVENT_FLAGS = 0xD7B7  # wEventFlags (pret pokegold.sym / pokesilver.sym)
EVENT_FLAGS_BYTES = 256

# Map script engine (pret pokegold.sym — identical on Gold and Silver)
ADDR_MAP_STATUS = 0xD159  # wMapStatus
ADDR_MAP_EVENT_STATUS = 0xD15A  # wMapEventStatus
ADDR_SCRIPT_FLAGS = 0xD15B  # wScriptFlags
ADDR_ENABLED_PLAYER_EVENTS = 0xD15D  # wEnabledPlayerEvents
ADDR_SCRIPT_MODE = 0xD15E  # wScriptMode
ADDR_SCRIPT_RUNNING = 0xD15F  # wScriptRunning (player event type, not on/off)
ADDR_SCRIPT_BANK = 0xD160  # wScriptBank
ADDR_SCRIPT_POS = 0xD161  # wScriptPos (16-bit)
ADDR_SCRIPT_DELAY = 0xD174  # wScriptDelay
ADDR_DEFERRED_SCRIPT_BANK = 0xD175  # wDeferredScriptBank
ADDR_DEFERRED_SCRIPT_ADDR = 0xD176  # wDeferredScriptAddr (16-bit)
ADDR_JOYPAD_DISABLE = 0xD8BA  # wJoypadDisable
ADDR_PLAYERS_HOUSE_1F_SCENE_ID = 0xD6CD  # wPlayersHouse1FSceneID
ADDR_MUSIC_PLAYING = 0xC000  # wMusicPlaying (WRAM0)

PLAYERS_HOUSE_1F_DOOR = (6, 7)

PARTYMON_STRUCT_LENGTH = 48
PARTYMON_LEVEL_OFFSET = 31
PARTYMON_HP_OFFSET = 34

SPECIES_NAMES: dict[int, str] = {
    1: "Bulbasaur",
    4: "Charmander",
    7: "Squirtle",
    16: "Pidgey",
    19: "Rattata",
    25: "Pikachu",
    152: "Chikorita",
    155: "Cyndaquil",
    158: "Totodile",
    161: "Sentret",
    163: "Hoothoot",
}

MAP_NAMES: dict[tuple[int, int], str] = {
    (MAPGROUP_NEW_BARK, MAP_PLAYERS_HOUSE_2F): "Player's House 2F",
    (MAPGROUP_NEW_BARK, MAP_PLAYERS_HOUSE_1F): "Player's House 1F",
    (MAPGROUP_NEW_BARK, MAP_NEW_BARK_TOWN): "New Bark Town",
    (MAPGROUP_NEW_BARK, MAP_ROUTE_29): "Route 29",
    (1, 2): "Cherrygrove City",
    (1, 3): "Route 30",
    (1, 4): "Violet City",
}


def coords_playable(x: int, y: int, *, facing: int | None = None) -> bool:
    """True when map coordinates look like a real overworld tile position."""
    if x > MAX_PLAYABLE_COORD or y > MAX_PLAYABLE_COORD:
        return False
    if facing is not None and facing == INVALID_FACING:
        return False
    return True

JOHTO_BADGE_NAMES = [
    "Zephyr",
    "Hive",
    "Plain",
    "Fog",
    "Storm",
    "Mineral",
    "Glacier",
    "Rising",
]

ITEM_NAMES: dict[int, str] = {
    1: "Master Ball",
    2: "Ultra Ball",
    3: "BrightPowder",
    4: "Great Ball",
    5: "Poke Ball",
    13: "Potion",
    14: "Super Potion",
}


class MemoryReader(Protocol):
    def read_byte(self, address: int) -> int: ...


class ByteArrayReader:
    """Read bytes from a flat address->byte mapping (for tests)."""

    def __init__(self, memory: dict[int, int]):
        self._memory = memory

    def read_byte(self, address: int) -> int:
        return self._memory.get(address, 0)


class PyBoyMemoryReader:
    """Adapter for PyBoy memory access."""

    def __init__(self, pyboy):
        self._pyboy = pyboy

    def read_byte(self, address: int) -> int:
        return int(self._pyboy.memory[address])


def _bcd_to_int(b0: int, b1: int, b2: int) -> int:
    digits = []
    for byte in (b2, b1, b0):
        digits.append((byte >> 4) & 0x0F)
        digits.append(byte & 0x0F)
    value = 0
    for d in digits:
        if d > 9:
            return 0
        value = value * 10 + d
    return value


def _decode_badges(bitfield: int, names: list[str]) -> list[str]:
    earned = []
    for i, name in enumerate(names):
        if bitfield & (1 << i):
            earned.append(name)
    return earned


def has_event_flag(reader: MemoryReader, flag_index: int) -> bool:
    """Return True when a pret event flag bit is set."""
    if flag_index < 0:
        return False
    byte_addr = ADDR_EVENT_FLAGS + (flag_index // 8)
    bit = flag_index % 8
    return bool(reader.read_byte(byte_addr) & (1 << bit))


def _read_event_flags(reader: MemoryReader, limit: int = 16) -> list[int]:
    flags = []
    for i in range(EVENT_FLAGS_BYTES):
        byte_val = reader.read_byte(ADDR_EVENT_FLAGS + i)
        for bit in range(8):
            if byte_val & (1 << bit):
                flags.append(i * 8 + bit)
                if len(flags) >= limit:
                    return flags
    return flags


class GoldStateReader:
    """Parse Gen 2 WRAM into a structured GameState."""

    def __init__(self, reader: MemoryReader, frame_count: int = 0):
        self._reader = reader
        self._frame_count = frame_count

    def read_at(self, frame_count: int) -> GameState:
        """Read GameState tagging the supplied emulation frame counter."""
        self._frame_count = frame_count
        return self.read()

    def read_player(self) -> PlayerState:
        r = self._reader
        map_group = r.read_byte(ADDR_MAP_GROUP)
        map_id = r.read_byte(ADDR_MAP_NUMBER)
        money = _bcd_to_int(
            r.read_byte(ADDR_MONEY),
            r.read_byte(ADDR_MONEY + 1),
            r.read_byte(ADDR_MONEY + 2),
        )
        return PlayerState(
            map_group=map_group,
            map_id=map_id,
            map_name=MAP_NAMES.get((map_group, map_id), f"Map {map_group}:{map_id}"),
            x=r.read_byte(ADDR_X_COORD),
            y=r.read_byte(ADDR_Y_COORD),
            facing=r.read_byte(ADDR_FACING),
            money=money,
        )

    def read_party(self) -> tuple[int, list[PartyMember]]:
        r = self._reader
        count = r.read_byte(ADDR_PARTY_COUNT)
        members: list[PartyMember] = []
        for i in range(min(count, 6)):
            species_id = r.read_byte(ADDR_PARTY_SPECIES + i)
            if species_id == 0:
                break
            base = ADDR_PARTY_MON1 + i * PARTYMON_STRUCT_LENGTH
            hp = r.read_byte(base + PARTYMON_HP_OFFSET) | (
                r.read_byte(base + PARTYMON_HP_OFFSET + 1) << 8
            )
            max_hp = r.read_byte(base + PARTYMON_HP_OFFSET + 2) | (
                r.read_byte(base + PARTYMON_HP_OFFSET + 3) << 8
            )
            level = r.read_byte(base + PARTYMON_LEVEL_OFFSET)
            members.append(
                PartyMember(
                    species_id=species_id,
                    species_name=SPECIES_NAMES.get(species_id, f"Species#{species_id}"),
                    level=level,
                    hp=hp,
                    max_hp=max_hp,
                )
            )
        return count, members

    def read_inventory(self) -> list[InventoryItem]:
        r = self._reader
        num_items = r.read_byte(ADDR_NUM_ITEMS)
        items: list[InventoryItem] = []
        for i in range(min(num_items, 20)):
            item_id = r.read_byte(ADDR_ITEMS + i * 2)
            quantity = r.read_byte(ADDR_ITEMS + i * 2 + 1)
            if item_id == 0:
                break
            items.append(
                InventoryItem(
                    item_id=item_id,
                    item_name=ITEM_NAMES.get(item_id, f"Item#{item_id}"),
                    quantity=quantity,
                )
            )
        return items

    def read_battle(self) -> BattleState:
        r = self._reader
        battle_mode = r.read_byte(ADDR_BATTLE_MODE)
        if battle_mode == 0:
            return BattleState(in_battle=False, phase=BattlePhase.NONE)

        enemy_species = r.read_byte(ADDR_ENEMY_SPECIES)
        enemy_hp = r.read_byte(ADDR_ENEMY_HP) | (r.read_byte(ADDR_ENEMY_HP + 1) << 8)
        enemy_max_hp = r.read_byte(ADDR_ENEMY_MAX_HP) | (
            r.read_byte(ADDR_ENEMY_MAX_HP + 1) << 8
        )

        phase = BattlePhase.WILD
        if battle_mode in (2, 3):
            phase = BattlePhase.TRAINER
        elif battle_mode == 4:
            phase = BattlePhase.GYM

        player_hp = 0
        player_max_hp = 0
        count = r.read_byte(ADDR_PARTY_COUNT)
        if count > 0:
            base = ADDR_PARTY_MON1
            player_hp = r.read_byte(base + PARTYMON_HP_OFFSET) | (
                r.read_byte(base + PARTYMON_HP_OFFSET + 1) << 8
            )
            player_max_hp = r.read_byte(base + PARTYMON_HP_OFFSET + 2) | (
                r.read_byte(base + PARTYMON_HP_OFFSET + 3) << 8
            )

        return BattleState(
            in_battle=True,
            phase=phase,
            player_active_hp=player_hp,
            player_active_max_hp=player_max_hp,
            enemy_species_id=enemy_species,
            enemy_species_name=SPECIES_NAMES.get(enemy_species, f"Species#{enemy_species}"),
            enemy_hp=enemy_hp,
            enemy_max_hp=enemy_max_hp,
            can_run=phase == BattlePhase.WILD,
        )

    def read_script_state(self) -> dict[str, int | bool]:
        r = self._reader
        script_flags = r.read_byte(ADDR_SCRIPT_FLAGS)
        script_mode = r.read_byte(ADDR_SCRIPT_MODE)
        script_running = r.read_byte(ADDR_SCRIPT_RUNNING)
        script_pos = r.read_byte(ADDR_SCRIPT_POS) | (r.read_byte(ADDR_SCRIPT_POS + 1) << 8)
        joypad_disable = r.read_byte(ADDR_JOYPAD_DISABLE)
        mom_scene_complete = has_event_flag(r, EVENT_PLAYERS_HOUSE_MOM_1)
        init_events = has_event_flag(r, EVENT_INITIALIZED_EVENTS)
        script_active = bool(script_flags & SCRIPT_FLAG_SCRIPT_RUNNING)
        return {
            "script_flags": script_flags,
            "script_mode": script_mode,
            "script_running": script_running,
            "script_pos": script_pos,
            "script_active": script_active,
            "joypad_disable": joypad_disable,
            "music_playing": r.read_byte(ADDR_MUSIC_PLAYING) != 0,
            "mom_scene_complete": mom_scene_complete,
            "init_events_complete": init_events,
            "in_script": script_active
            and script_mode in (SCRIPT_READ, SCRIPT_WAIT_MOVEMENT, SCRIPT_WAIT),
        }

    def read(self) -> GameState:
        player = self.read_player()
        party_count, party = self.read_party()
        johto = self._reader.read_byte(ADDR_JOHTO_BADGES)
        kanto = self._reader.read_byte(ADDR_KANTO_BADGES)
        script_meta = self.read_script_state()
        in_text_box = (
            script_meta["script_mode"] == SCRIPT_READ and script_meta["script_active"]
        ) or (
            player.map_group == MAPGROUP_NEW_BARK
            and player.map_id == MAP_PLAYERS_HOUSE_1F
            and not script_meta["mom_scene_complete"]
            and script_meta["script_active"]
        )
        return GameState(
            player=player,
            party=party,
            party_count=party_count,
            inventory=self.read_inventory(),
            johto_badges=johto,
            kanto_badges=kanto,
            badge_names=_decode_badges(johto, JOHTO_BADGE_NAMES)
            + _decode_badges(kanto, ["Boulder", "Cascade", "Thunder", "Rainbow"]),
            event_flags_set=_read_event_flags(self._reader),
            battle=self.read_battle(),
            in_text_box=in_text_box,
            frame_count=self._frame_count,
            raw_metadata=script_meta,
        )