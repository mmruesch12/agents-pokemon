"""LangChain tool wrappers bound to the emulator control plane."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

if TYPE_CHECKING:
    from src.emulator.pyboy_wrapper import PyBoyWrapper

_emulator: PyBoyWrapper | None = None


def bind_emulator(emu: PyBoyWrapper) -> None:
    global _emulator
    _emulator = emu


def unbind_emulator() -> None:
    global _emulator
    _emulator = None


def get_bound_emulator() -> PyBoyWrapper:
    if _emulator is None:
        raise RuntimeError("Emulator not bound. Call bind_emulator() first.")
    return _emulator


def _require_emu() -> PyBoyWrapper:
    return get_bound_emulator()


@tool
def get_state() -> dict[str, Any]:
    """Read current structured game state from emulator RAM."""
    state = _require_emu().get_game_state()
    return state.model_dump()


@tool
def press_button(button: str) -> dict[str, Any]:
    """Press a Game Boy button: a, b, start, select, up, down, left, right."""
    emu = _require_emu()
    emu.press_button(button)  # type: ignore[arg-type]
    return {"button": button, "frame_count": emu.frame_count}


@tool
def advance_frames(n: int = 1) -> dict[str, int]:
    """Advance emulation by N frames without button input."""
    emu = _require_emu()
    frames = emu.advance_frames(max(1, n))
    return {"frame_count": frames}


@tool
def navigate_to(target_x: int, target_y: int) -> dict[str, Any]:
    """Navigate toward target coordinates using simple pathfinding."""
    from src.graph.pathfinding import find_path, direction_to_button

    emu = _require_emu()
    state = emu.get_game_state()
    path = find_path(
        state.player.x,
        state.player.y,
        target_x,
        target_y,
        map_key=state.map_key,
    )
    buttons_pressed = []
    for direction in path[:10]:
        btn = direction_to_button(direction)
        emu.press_button(btn)  # type: ignore[arg-type]
        buttons_pressed.append(btn)

    new_state = emu.get_game_state()
    return {
        "buttons_pressed": buttons_pressed,
        "from": (state.player.x, state.player.y),
        "to": (new_state.player.x, new_state.player.y),
        "target": (target_x, target_y),
    }


@tool
def battle_decide(action: str = "fight") -> dict[str, Any]:
    """Make a battle decision: fight, run, switch, or item."""
    emu = _require_emu()
    state = emu.get_game_state()
    if not state.battle.in_battle:
        return {"action": action, "result": "not_in_battle"}

    action_map = {
        "fight": "a",
        "run": "down",  # simplified menu navigation
        "switch": "down",
        "item": "down",
    }
    btn = action_map.get(action.lower(), "a")
    emu.press_button(btn)  # type: ignore[arg-type]
    if action.lower() == "fight":
        emu.press_button("a")
    return {
        "action": action,
        "buttons": [btn, "a"] if action.lower() == "fight" else [btn],
        "frame_count": emu.frame_count,
    }


@tool
def save_emulator_state(name: str) -> dict[str, str]:
    """Save emulator state to disk."""
    path = _require_emu().save_state(name)
    return {"saved": str(path)}


@tool
def load_emulator_state(name: str) -> dict[str, str]:
    """Load emulator state from disk."""
    _require_emu().load_state(name)
    return {"loaded": name}


ALL_TOOLS = [
    get_state,
    press_button,
    advance_frames,
    navigate_to,
    battle_decide,
    save_emulator_state,
    load_emulator_state,
]