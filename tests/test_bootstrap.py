"""Tests for intro bootstrap helpers."""

from __future__ import annotations

from src.emulator.bootstrap import (
    MAP_GROUP_ADDR,
    MAP_NUMBER_ADDR,
    MOVEMENT_PROBE_ADDR,
    in_loaded_map,
    is_bootstrap_done,
    needs_bootstrap,
    pick_bootstrap_button,
    run_bootstrap,
)
from src.graph.state import initial_agent_state
from src.state.models import GameState


class ProbeEmulator:
    """Minimal emulator stub for bootstrap movement probing."""

    class _Memory:
        def __init__(self, backing: dict[int, int]):
            self._backing = backing

        def __getitem__(self, address: int) -> int:
            return self._backing.get(address, 0)

    class _PyBoy:
        def __init__(self, outer: "ProbeEmulator"):
            self._outer = outer

        @property
        def memory(self):
            return ProbeEmulator._Memory(self._outer._memory)

    def __init__(self, memory: dict[int, int] | None = None):
        self._memory = dict(memory or {})
        self._frame_count = 0
        self._pyboy = self._PyBoy(self)

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def tick(self, frames: int = 1) -> int:
        self._frame_count += frames
        return self._frame_count

    def press_button(self, button: str, *, hold_frames: int = 2) -> None:
        if button == "down":
            self._memory[MOVEMENT_PROBE_ADDR] = self._memory.get(MOVEMENT_PROBE_ADDR, 0) + 1
        self._frame_count += hold_frames + 1

    def get_game_state(self) -> GameState:
        from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

        return GoldStateReader(ByteArrayReader(self._memory), frame_count=self._frame_count).read()


def test_needs_bootstrap_fresh_rom():
    gs = GameState()
    assert needs_bootstrap(gs, {}) is True


def test_needs_bootstrap_skips_when_complete():
    gs = GameState()
    state = {"bootstrap_complete": True}
    assert needs_bootstrap(gs, state) is False


def test_needs_bootstrap_skips_with_party(new_bark_ram: dict):
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    assert needs_bootstrap(gs, {}) is False


def test_needs_bootstrap_skips_when_movement_ready():
    gs = GameState(raw_metadata={"movement_ready": True})
    assert needs_bootstrap(gs, {}) is False


def test_in_loaded_map_requires_nonzero_map():
    emu = ProbeEmulator()
    assert in_loaded_map(emu) is False
    emu._memory[MAP_GROUP_ADDR] = 3
    emu._memory[MAP_NUMBER_ADDR] = 4
    assert in_loaded_map(emu) is True


def test_pick_bootstrap_button_cycles():
    buttons = {pick_bootstrap_button(i) for i in range(120)}
    assert "a" in buttons
    assert "start" in buttons


def test_pick_bootstrap_button_indoor_bias():
    buttons = {pick_bootstrap_button(i, loaded_map=(3, 4)) for i in range(30)}
    assert "down" in buttons
    assert "a" in buttons


def test_run_bootstrap_skips_when_party_present(new_bark_ram: dict):
    emu = ProbeEmulator(new_bark_ram)
    result = run_bootstrap(emu, max_actions=0, title_wait_frames=0)
    assert result.actions_taken == 0
    assert result.movement_ready is False


def test_run_bootstrap_detects_loaded_map():
    emu = ProbeEmulator({MAP_GROUP_ADDR: 3, MAP_NUMBER_ADDR: 4, MOVEMENT_PROBE_ADDR: 0})
    result = run_bootstrap(emu, max_actions=3, title_wait_frames=0)
    assert result.map_loaded is True
    assert result.success is True
    assert result.movement_ready is False


def test_is_bootstrap_done_requires_minimum_actions():
    emu = ProbeEmulator({MAP_GROUP_ADDR: 3, MAP_NUMBER_ADDR: 4})
    gs = GameState()
    assert is_bootstrap_done(emu, gs, {"bootstrap_action_index": 5}) is False


def test_is_bootstrap_done_after_indoor_cap():
    emu = ProbeEmulator({MAP_GROUP_ADDR: 3, MAP_NUMBER_ADDR: 4})
    gs = GameState()
    assert is_bootstrap_done(emu, gs, {"bootstrap_action_index": 80}) is True


def test_supervisor_routes_to_bootstrap_for_fresh_game():
    from src.graph.nodes import supervisor_node

    gs = GameState()
    state = initial_agent_state(gs)
    result = supervisor_node(state)
    assert result["next_node"] == "bootstrap"
    assert result["phase"] == "bootstrap"


def test_supervisor_routes_to_navigator_when_bootstrapped(new_bark_ram: dict):
    from src.graph.nodes import supervisor_node
    from src.state.gold_state_reader import ByteArrayReader, GoldStateReader

    gs = GoldStateReader(ByteArrayReader(new_bark_ram)).read()
    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    result = supervisor_node(state)
    assert result["next_node"] == "navigator"