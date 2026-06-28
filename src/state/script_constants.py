"""Gen 2 script / event constants (pret/pokegold, verified on live Silver)."""

from __future__ import annotations

# wScriptMode values (constants/ram_constants.asm)
SCRIPT_OFF = 0
SCRIPT_READ = 1
SCRIPT_WAIT_MOVEMENT = 2
SCRIPT_WAIT = 3

# Event flag indices (constants/event_flags.asm const_def order)
EVENT_INITIALIZED_EVENTS = 53
EVENT_GOT_A_POKEMON_FROM_ELM = 26
EVENT_GOT_CYNDAQUIL_FROM_ELM = 27
EVENT_GOT_TOTODILE_FROM_ELM = 28
EVENT_GOT_CHIKORITA_FROM_ELM = 29
EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON = 30
EVENT_GAVE_MYSTERY_EGG_TO_ELM = 31
EVENT_PLAYERS_HOUSE_MOM_1 = 1735
EVENT_PLAYERS_HOUSE_MOM_2 = 1736
EVENT_RIVAL_NEW_BARK_TOWN = 1725
EVENT_MR_POKEMONS_HOUSE_OAK = 1737
EVENT_EARLS_ACADEMY_EARL = 1739

# MeetMomScript entry position (live Silver cold boot)
MOM_SCENE_ENTRY_POS = (9, 1)

# wScriptFlags bits (pret constants/ram_constants.asm)
SCRIPT_FLAG_SCRIPT_RUNNING = 1 << 2
SCRIPT_FLAG_RUN_DEFERRED = 1 << 3

# wJoypadDisable bits that actually block UpdateJoypad (pret home/joypad.asm)
JOYPAD_DISABLE_MON_FAINT_F = 6
JOYPAD_DISABLE_SGB_TRANSFER_F = 7
JOYPAD_DISABLE_INPUT_MASK = (1 << 4) | (1 << JOYPAD_DISABLE_MON_FAINT_F) | (
    1 << JOYPAD_DISABLE_SGB_TRANSFER_F
)


def joypad_input_blocked(joypad_disable: int) -> bool:
    """True when pret would skip reading the joypad this frame."""
    return bool(joypad_disable & JOYPAD_DISABLE_INPUT_MASK)