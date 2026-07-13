"""Hold-matrix tests: corridor maps must not idle; first gym is terminal.

Drives shipped `_hold_phase_satisfied` / phase `is_satisfied` / milestones only.
"""

from __future__ import annotations

from src.graph.nodes import _check_milestone, _hold_phase_satisfied, supervisor_node
from src.graph.phases import early_progression
from src.graph.state import initial_agent_state
from src.state.gold_state_reader import (
    MAP_KEY_CHERRYGROVE_CITY,
    MAP_KEY_ROUTE_30,
    MAP_KEY_ROUTE_31,
    MAP_KEY_VIOLET_CITY,
    MAP_KEY_VIOLET_GYM,
)
from src.state.models import GameState

# map_key, group, map_id, expect_hold
HOLD_MATRIX = (
    (MAP_KEY_CHERRYGROVE_CITY, 26, 3, False),
    (MAP_KEY_ROUTE_30, 26, 1, False),
    (MAP_KEY_ROUTE_31, 26, 2, False),
    (MAP_KEY_VIOLET_CITY, 10, 5, False),
    (MAP_KEY_VIOLET_GYM, 10, 7, True),
)


def _post_rival_state(gs: GameState) -> dict:
    from src.memory.landmarks import seed_static_map_landmarks

    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["starter_quest_complete"] = True
    state["early_progression_complete"] = False
    seed_static_map_landmarks(state)
    return state


def test_hold_matrix_corridor_false_gym_true():
    for map_key, group, map_id, expect_hold in HOLD_MATRIX:
        gs = GameState(
            player={"map_group": group, "map_id": map_id, "x": 8, "y": 8},
            party_count=1,
            raw_metadata={"has_starter": True},
        )
        assert gs.map_key == map_key
        state = _post_rival_state(gs)
        assert early_progression.is_satisfied(gs, state) is expect_hold, map_key
        assert _hold_phase_satisfied(gs, state) is expect_hold, map_key
        next_node = supervisor_node(state)["next_node"]
        if expect_hold:
            assert next_node == "idle", map_key
        else:
            assert next_node != "idle", map_key


def test_milestone_vocabulary_includes_corridor_and_gym():
    vocab = {
        early_progression.MILESTONE_REACHED_CHERRYGROVE,
        early_progression.MILESTONE_REACHED_ROUTE_31,
        early_progression.MILESTONE_REACHED_VIOLET,
        early_progression.MILESTONE_ENTERED_FIRST_GYM,
    }
    for map_key, group, map_id, _ in HOLD_MATRIX:
        if map_key == MAP_KEY_ROUTE_30:
            continue  # no dedicated first-visit milestone required for R30
        gs = GameState(
            player={"map_group": group, "map_id": map_id, "x": 5, "y": 5},
            party_count=1,
        )
        state = _post_rival_state(gs)
        ms = _check_milestone(gs, state, [map_key])
        assert ms in vocab, (map_key, ms)
