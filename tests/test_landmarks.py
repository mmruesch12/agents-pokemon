"""Tests for landmark memory, gating, and navigator context."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.exploration import exploration_target
from src.graph.llm import llm_navigate
from src.graph.nodes import (
    _gate_starter_quest_target,
    _navigation_target,
    memory_node,
    navigator_node,
)
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_INTERIOR_ID,
    discover_elms_lab_landmarks,
    make_landmark,
    normalize_elms_lab_entrance_coords,
)
from src.memory.long_term_memory import LongTermMemory
from src.state.gold_state_reader import MAP_KEY_ELMS_LAB, MAP_KEY_NEW_BARK_TOWN
from src.state.models import GameState


def test_landmark_roundtrip_and_retrieval():
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_landmark(
            {
                "id": ELMS_LAB_ENTRANCE_ID,
                "name": "Elm's Lab",
                "map_key": "24:5",
                "x": 5,
                "y": 2,
                "kind": "interior",
            }
        )
        hits = mem.retrieve_landmarks("lab")
        assert any("Lab" in str(entry.get("name", "")) for entry in hits)


def test_navigation_without_landmark_uses_quest_hint():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert _navigation_target(gs, state=state) == starter_quest.NEW_BARK_LAB_APPROACH
    assert not state.get("known_landmarks")


def test_gated_phase_target_ignores_landmark_on_wrong_map():
    gs = GameState(player={"map_group": 24, "map_id": 5, "x": 4, "y": 8})
    state = {
        "known_landmarks": [
            make_landmark(
                landmark_id=ELMS_LAB_ENTRANCE_ID,
                name="Elm's Lab entrance",
                map_key=MAP_KEY_NEW_BARK_TOWN,
                x=6,
                y=3,
                kind="building_entrance",
            )
        ]
    }
    from src.graph.exploration import gated_phase_target

    target = gated_phase_target(
        gs,
        starter_quest.NEW_BARK_LAB_WARP,
        state=state,
        landmark_id=ELMS_LAB_ENTRANCE_ID,
    )
    assert target != (6, 3)


def test_navigation_uses_alt_door_entrance_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=ELMS_LAB_ENTRANCE_ID,
            name="Elm's Lab entrance",
            map_key=MAP_KEY_NEW_BARK_TOWN,
            x=5,
            y=3,
            kind="building_entrance",
        )
    ]
    assert _navigation_target(gs, state=state) == (5, 4)


def test_navigation_uses_discovered_entrance_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=ELMS_LAB_ENTRANCE_ID,
            name="Elm's Lab entrance",
            map_key=MAP_KEY_NEW_BARK_TOWN,
            x=6,
            y=3,
            kind="building_entrance",
        )
    ]
    assert _navigation_target(gs, state=state) == starter_quest.NEW_BARK_LAB_APPROACH


def test_normalize_elms_lab_entrance_snaps_adjacent_tiles():
    assert normalize_elms_lab_entrance_coords(MAP_KEY_NEW_BARK_TOWN, 6, 4) == (
        MAP_KEY_NEW_BARK_TOWN,
        6,
        3,
    )
    assert normalize_elms_lab_entrance_coords(MAP_KEY_NEW_BARK_TOWN, 5, 4) == (
        MAP_KEY_NEW_BARK_TOWN,
        5,
        3,
    )
    assert normalize_elms_lab_entrance_coords(MAP_KEY_NEW_BARK_TOWN, 6, 3) == (
        MAP_KEY_NEW_BARK_TOWN,
        6,
        3,
    )


def test_discover_elms_lab_landmarks_normalizes_entrance_from_below():
    gs = GameState(player={"map_group": 24, "map_id": 5, "x": 4, "y": 8})
    landmarks = discover_elms_lab_landmarks(
        gs,
        entrance_map_key=MAP_KEY_NEW_BARK_TOWN,
        entrance_x=6,
        entrance_y=4,
    )
    entrance = next(entry for entry in landmarks if entry.get("id") == ELMS_LAB_ENTRANCE_ID)
    assert entrance["x"] == 6
    assert entrance["y"] == 3


def test_memory_node_discovers_lab_landmarks_on_first_visit(monkeypatch):
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 8, "map_name": "Elm's Lab"},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = [MAP_KEY_NEW_BARK_TOWN]
    state["last_map_transition"] = {
        "from_map": MAP_KEY_NEW_BARK_TOWN,
        "from_pos": {"map_key": MAP_KEY_NEW_BARK_TOWN, "x": 6, "y": 4},
        "to_map": MAP_KEY_ELMS_LAB,
        "to_pos": {"x": 4, "y": 8},
    }
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POKEMON_MEMORY_DIR", tmp)
        state = memory_node(state)
    landmarks = state.get("known_landmarks", [])
    assert any(entry.get("id") == ELMS_LAB_INTERIOR_ID for entry in landmarks)
    assert any(entry.get("id") == ELMS_LAB_ENTRANCE_ID for entry in landmarks)
    assert state.get("memory_retrievals")


def test_navigator_attaches_landmark_context(monkeypatch):
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=ELMS_LAB_ENTRANCE_ID,
            name="Elm's Lab entrance",
            map_key=MAP_KEY_NEW_BARK_TOWN,
            x=6,
            y=3,
            kind="building_entrance",
        )
    ]
    captured: dict[str, object] = {}

    def fake_navigate(gs_arg, state_arg, candidates, landmarks, *, target=None):
        captured["landmarks"] = landmarks
        captured["target"] = target
        return None

    monkeypatch.setattr("src.graph.nodes.llm_navigate", fake_navigate)
    navigator_node(state)
    assert captured["landmarks"]
    assert captured["target"] == starter_quest.NEW_BARK_LAB_APPROACH


def test_llm_navigate_prompt_includes_landmarks(monkeypatch):
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 8, "y": 12})
    state = initial_agent_state(gs)
    prompts: list[str] = []

    class FakeLLM:
        def invoke(self, messages, config=None):
            prompts.append(messages[-1].content)
            return type("Resp", (), {"content": "right"})()

    monkeypatch.setattr("src.graph.llm.get_chat_model", lambda: FakeLLM())
    llm_navigate(
        gs,
        state,
        ["right"],
        [
            make_landmark(
                landmark_id=ELMS_LAB_ENTRANCE_ID,
                name="Elm's Lab entrance",
                map_key=MAP_KEY_NEW_BARK_TOWN,
                x=6,
                y=3,
                kind="building_entrance",
            )
        ],
        target=(6, 3),
    )
    assert "Known landmarks" in prompts[0]


def test_interior_target_gated_until_lab_discovered():
    gs = GameState(
        player={"map_group": 24, "map_id": 5, "x": 4, "y": 8},
        raw_metadata={"has_starter": False},
    )
    assert _gate_starter_quest_target(gs, starter_quest.STARTER_BALL_TILE, state={}) != (
        starter_quest.STARTER_BALL_TILE
    )
    state = {"known_landmarks": discover_elms_lab_landmarks(gs)}
    assert (
        _gate_starter_quest_target(gs, starter_quest.STARTER_BALL_TILE, state=state)
        == starter_quest.STARTER_BALL_TILE
    )


def test_exploration_hint_targets_lab_warp():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 13, "y": 6})
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert (
        exploration_target(gs, state, hint_tile=starter_quest.NEW_BARK_LAB_WARP)
        == starter_quest.NEW_BARK_LAB_WARP
    )