"""Unit tests for house_exit phase module (routing, navigation, post-exit handoff)."""

from __future__ import annotations

from src.graph.phases import house_exit
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    PLAYERS_HOUSE_1F_DOOR,
)
from src.state.models import GameState


def _gs(
    group: int,
    map_id: int,
    x: int,
    y: int,
    *,
    mom_done: bool = False,
    map_name: str = "",
) -> GameState:
    return GameState(
        player={
            "map_group": group,
            "map_id": map_id,
            "x": x,
            "y": y,
            "map_name": map_name or f"map_{group}_{map_id}",
        },
        raw_metadata={"mom_scene_complete": mom_done},
    )


def test_in_house_exit_2f_and_1f():
    state = initial_agent_state()
    assert house_exit.in_house_exit(_gs(24, 7, 3, 4), state) is True
    assert house_exit.in_house_exit(_gs(24, 6, 9, 1), state) is True
    assert house_exit.in_house_exit(_gs(24, 4, 10, 6), state) is False


def test_in_house_exit_false_after_complete_flag():
    state = {"house_exit_complete": True}
    assert house_exit.in_house_exit(_gs(24, 6, 6, 7), state) is False


def test_force_interactor_during_mom_scene():
    gs = _gs(24, 6, 9, 1, mom_done=False)
    state = initial_agent_state(gs)
    assert house_exit.force_interactor(gs, state) is True


def test_navigation_target_2f_stairs():
    gs = _gs(24, 7, 3, 4)
    assert house_exit.navigation_target(gs) == house_exit.STAIRS_2F


def test_navigation_target_1f_mom_hold_position():
    gs = _gs(24, 6, 9, 1, mom_done=False)
    assert house_exit.navigation_target(gs) == (9, 1)


def test_navigation_target_1f_door_after_mom():
    kitchen = _gs(24, 6, 7, 2, mom_done=True)
    assert house_exit.navigation_target(kitchen) == house_exit.PLAYERS_HOUSE_1F_CORRIDOR
    at_door_row = _gs(24, 6, 6, 6, mom_done=True)
    assert house_exit.navigation_target(at_door_row) == PLAYERS_HOUSE_1F_DOOR


def test_navigation_target_new_bark_deferred_to_explorer():
    gs = _gs(24, 4, 8, 12)
    assert house_exit.navigation_target(gs) is None
    assert house_exit.navigation_target(gs, state={"house_exit_complete": True}) is None


def test_door_exit_direction_after_mom_at_door():
    gs = _gs(24, 6, 6, 7, mom_done=True)
    assert house_exit.door_exit_direction(gs) == "down"


def test_blocked_stairs_up_during_mom_at_east_end():
    gs = _gs(24, 6, 9, 1, mom_done=False)
    assert house_exit.blocked_stairs_up(gs) is True
    gs_done = _gs(24, 6, 9, 1, mom_done=True)
    # After Mom flag, stairs stay blocked until house_exit_complete (no 1F↔2F thrash).
    assert house_exit.blocked_stairs_up(gs_done) is True
    assert house_exit.blocked_stairs_up(gs_done, {"house_exit_complete": True}) is False


def test_on_house_exit_complete_sets_flag_only():
    gs = _gs(24, 4, 13, 5, map_name="New Bark Town")
    state = initial_agent_state(gs)
    state["stuck_count"] = 8
    state["should_replan"] = True
    house_exit.on_house_exit_complete(state, gs)
    assert state["house_exit_complete"] is True
    assert state["stuck_count"] == 8
    assert state["should_replan"] is True


def test_format_map_context_includes_map_key():
    gs = _gs(24, 7, 3, 4, map_name="Player's House 2F")
    assert house_exit.format_map_context(gs) == "24:7 Player's House 2F (3,4)"


def test_house_milestone_new_bark_first_visit():
    gs = _gs(24, 4, 13, 5, map_name="New Bark Town")
    maps = [MAP_KEY_PLAYERS_HOUSE_2F, MAP_KEY_PLAYERS_HOUSE_1F, MAP_KEY_NEW_BARK_TOWN]
    assert house_exit.house_milestone(gs, maps) == house_exit.HOUSE_EXIT_MILESTONE
    assert house_exit.house_milestone(gs, [MAP_KEY_NEW_BARK_TOWN]) is None


def test_planner_allows_llm_blocked_in_house():
    gs = _gs(24, 6, 9, 1)
    state = initial_agent_state(gs)
    assert house_exit.planner_allows_llm(gs, state) is False


def test_is_satisfied_requires_new_bark_exterior():
    gs = _gs(24, 4, 13, 5, map_name="New Bark Town")
    assert house_exit.is_satisfied(gs, {"house_exit_complete": True}) is True
    assert house_exit.is_satisfied(gs, {"house_exit_complete": False}) is False
    gs_house = _gs(24, 6, 9, 1)
    assert house_exit.is_satisfied(gs_house, {"house_exit_complete": True}) is False


