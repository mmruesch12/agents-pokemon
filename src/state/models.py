"""Pydantic models for structured game state."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BattlePhase(str, Enum):
    NONE = "none"
    WILD = "wild"
    TRAINER = "trainer"
    GYM = "gym"


class PartyMember(BaseModel):
    species_id: int
    species_name: str = ""
    level: int = 1
    hp: int = 0
    max_hp: int = 0
    moves: list[str] = Field(default_factory=list)


class InventoryItem(BaseModel):
    item_id: int
    item_name: str = ""
    quantity: int = 1


class BattleState(BaseModel):
    in_battle: bool = False
    phase: BattlePhase = BattlePhase.NONE
    player_active_hp: int = 0
    player_active_max_hp: int = 0
    enemy_species_id: int = 0
    enemy_species_name: str = ""
    enemy_hp: int = 0
    enemy_max_hp: int = 0
    can_run: bool = True


class PlayerState(BaseModel):
    map_group: int = 0
    map_id: int = 0
    map_name: str = ""
    x: int = 0
    y: int = 0
    facing: int = 0
    money: int = 0


class GameState(BaseModel):
    player: PlayerState = Field(default_factory=PlayerState)
    party: list[PartyMember] = Field(default_factory=list)
    party_count: int = 0
    inventory: list[InventoryItem] = Field(default_factory=list)
    johto_badges: int = 0
    kanto_badges: int = 0
    badge_names: list[str] = Field(default_factory=list)
    event_flags_set: list[int] = Field(default_factory=list)
    battle: BattleState = Field(default_factory=BattleState)
    in_menu: bool = False
    in_text_box: bool = False
    frame_count: int = 0
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def map_key(self) -> str:
        return f"{self.player.map_group}:{self.player.map_id}"

    @property
    def position_key(self) -> str:
        return f"{self.map_key}:{self.player.x}:{self.player.y}"

    @property
    def total_badges(self) -> int:
        return bin(self.johto_badges).count("1") + bin(self.kanto_badges).count("1")