"""Tests for landmark memory, gating, and navigator context."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.graph.exploration import exploration_target
from src.emulator.bootstrap import seed_bedroom_agent_state
from src.graph.llm import llm_navigate
from src.graph.navigation_resolve import resolve_landmark_navigation_target
from src.graph.nodes import _navigation_target, memory_node, navigator_node
from src.graph.state import initial_agent_state
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_INTERIOR_ID,
    MR_POKEMONS_HOUSE_ENTRANCE_ID,
    NEW_BARK_WEST_EXIT_ID,
    ROUTE_29_NORTH_GATE_ID,
    ROUTE_30_NORTH_GATE_ID,
    discover_elms_lab_landmarks,
    discover_mr_pokemon_entrance_landmark,
    discover_quest_transition_landmarks,
    make_landmark,
    normalize_elms_lab_entrance_coords,
)
from src.memory.long_term_memory import LongTermMemory
from src.state.gold_state_reader import MAP_KEY_MR_POKEMONS_HOUSE
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


def test_cold_bedroom_lab_nav():
    """Bootstrap seeds static lab entrance; nav uses landmark approach on New Bark."""
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state = seed_bedroom_agent_state(state, gs)
    state["house_exit_complete"] = True
    assert any(
        entry.get("id") == ELMS_LAB_ENTRANCE_ID
        for entry in state.get("known_landmarks", [])
    )
    assert _navigation_target(gs, state=state) == (6, 4)


def test_navigation_without_landmark_uses_exploration_frontier():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    target = _navigation_target(gs, state=state)
    assert target is not None
    assert target != (gs.player.x, gs.player.y)


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

    target = gated_phase_target(gs, (6, 3), state=state, landmark_id=ELMS_LAB_ENTRANCE_ID)
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
    assert _navigation_target(gs, state=state) == (6, 4)


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


def test_memory_node_records_entrance_on_lab_warp_discovery():
    """Runtime warp discovery merges entrance landmark (supplements bootstrap seed)."""
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
    state = memory_node(state)
    entrance = next(
        entry
        for entry in state.get("known_landmarks", [])
        if entry.get("id") == ELMS_LAB_ENTRANCE_ID
    )
    assert entrance["map_key"] == MAP_KEY_NEW_BARK_TOWN
    assert (entrance["x"], entrance["y"]) == (6, 3)


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
    assert captured["target"] == (6, 4)


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


def test_landmark_navigation_none_without_entrance():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert resolve_landmark_navigation_target(gs, state) is None
    target = _navigation_target(gs, state=state)
    assert target is not None
    assert target != (gs.player.x, gs.player.y)


def test_discover_quest_transition_landmarks_west_exit():
    landmarks = discover_quest_transition_landmarks(
        from_map="24:4",
        to_map="24:3",
        from_pos={"map_key": "24:4", "x": 0, "y": 8},
    )
    assert any(entry.get("id") == NEW_BARK_WEST_EXIT_ID for entry in landmarks)


def test_discover_quest_transition_landmarks_route_gates():
    route29 = discover_quest_transition_landmarks(
        from_map="24:3",
        to_map="26:1",
        from_pos={"map_key": "24:3", "x": 10, "y": 5},
    )
    assert any(entry.get("id") == ROUTE_29_NORTH_GATE_ID for entry in route29)

    route30 = discover_quest_transition_landmarks(
        from_map="26:1",
        to_map="26:10",
        from_pos={"map_key": "26:1", "x": 10, "y": 3},
    )
    assert any(entry.get("id") == ROUTE_30_NORTH_GATE_ID for entry in route30)
    assert not any(entry.get("id") == MR_POKEMONS_HOUSE_ENTRANCE_ID for entry in route30)


def test_discover_mr_pokemon_entrance_on_interior_map():
    gs = GameState(player={"map_group": 26, "map_id": 10, "x": 5, "y": 7})
    landmark = discover_mr_pokemon_entrance_landmark(gs)
    assert landmark["id"] == MR_POKEMONS_HOUSE_ENTRANCE_ID
    assert landmark["map_key"] == MAP_KEY_MR_POKEMONS_HOUSE
    assert (landmark["x"], landmark["y"]) == (5, 5)


def test_memory_node_discovers_mr_pokemon_entrance_on_first_visit(monkeypatch):
    gs = GameState(
        player={"map_group": 26, "map_id": 10, "x": 5, "y": 7, "map_name": "Mr. Pokemon's House"},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = ["24:4", "24:3", "26:1"]
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POKEMON_MEMORY_DIR", tmp)
        state = memory_node(state)
    entrance = next(
        entry
        for entry in state.get("known_landmarks", [])
        if entry.get("id") == MR_POKEMONS_HOUSE_ENTRANCE_ID
    )
    assert entrance["map_key"] == MAP_KEY_MR_POKEMONS_HOUSE
    assert (entrance["x"], entrance["y"]) == (5, 5)


def test_exploration_target_frontier_without_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    target = exploration_target(gs, state)
    assert target is not None
    assert target != (gs.player.x, gs.player.y)


def test_navigation_wrong_map_west_landmark_uses_frontier():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=NEW_BARK_WEST_EXIT_ID,
            name="New Bark Route 29 exit",
            map_key=MAP_KEY_NEW_BARK_TOWN,
            x=0,
            y=8,
            kind="map_visit",
        ),
        make_landmark(
            landmark_id=ROUTE_29_NORTH_GATE_ID,
            name="Route 29 north gate",
            map_key="24:3",
            x=10,
            y=5,
            kind="map_visit",
        ),
    ]
    target = _navigation_target(gs, state=state)
    assert target == (10, 5)
    assert target != (0, 8)


def test_hydrate_state_enables_west_exit_navigation():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_landmark(
            make_landmark(
                landmark_id=NEW_BARK_WEST_EXIT_ID,
                name="New Bark Route 29 exit",
                map_key="24:4",
                x=0,
                y=8,
                kind="map_visit",
            )
        )
        mem.add_landmark(
            make_landmark(
                landmark_id=ROUTE_29_NORTH_GATE_ID,
                name="Route 29 north gate",
                map_key="24:3",
                x=10,
                y=5,
                kind="map_visit",
            )
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        hydrated = mem.hydrate_state(state)
        assert _navigation_target(gs, state=hydrated) == (0, 8)
        gs_route = GameState(
            player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
            raw_metadata={"has_starter": True},
            party_count=1,
        )
        hydrated_route = mem.hydrate_state({**hydrated, "game_state": gs_route.model_dump()})
        assert _navigation_target(gs_route, state=hydrated_route) == (10, 5)
        assert _navigation_target(gs_route, state=hydrated_route) == (10, 5)


def test_hydrate_mr_entrance_enables_interior_navigation():
    from src.graph.exploration import gated_phase_target
    from src.memory.landmarks import find_landmark

    gs = GameState(
        player={"map_group": 26, "map_id": 10, "x": 5, "y": 7},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = LongTermMemory(data_dir=Path(tmp))
        mem.add_landmark(
            make_landmark(
                landmark_id=MR_POKEMONS_HOUSE_ENTRANCE_ID,
                name="Mr. Pokemon's House entrance",
                map_key=MAP_KEY_MR_POKEMONS_HOUSE,
                x=5,
                y=5,
                kind="building_entrance",
            )
        )
        state = initial_agent_state(gs)
        state["house_exit_complete"] = True
        hydrated = mem.hydrate_state(state)
        landmark = find_landmark(hydrated["known_landmarks"], landmark_id=MR_POKEMONS_HOUSE_ENTRANCE_ID)
        assert landmark is not None
        assert landmark["map_key"] == MAP_KEY_MR_POKEMONS_HOUSE
        assert gated_phase_target(
            gs, None, state=hydrated, landmark_id=MR_POKEMONS_HOUSE_ENTRANCE_ID
        ) == (5, 5)
        assert _navigation_target(gs, state=hydrated) == (5, 5)


def test_mr_entrance_discovery_persists_and_hydrates(monkeypatch):
    gs = GameState(
        player={"map_group": 26, "map_id": 10, "x": 5, "y": 7, "map_name": "Mr. Pokemon's House"},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = ["24:4", "24:3", "26:1"]
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POKEMON_MEMORY_DIR", tmp)
        state = memory_node(state)
        reloaded = LongTermMemory(data_dir=Path(tmp))
        fresh = initial_agent_state(gs)
        fresh["house_exit_complete"] = True
        hydrated = reloaded.hydrate_state(fresh)
        assert any(
            entry.get("id") == MR_POKEMONS_HOUSE_ENTRANCE_ID
            for entry in hydrated.get("known_landmarks", [])
        )
        assert _navigation_target(gs, state=hydrated) == (5, 5)


def test_memory_node_discovers_west_exit_on_route_transition(monkeypatch):
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12, "map_name": "Route 29"},
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = ["24:4"]
    state["last_map_transition"] = {
        "from_map": "24:4",
        "from_pos": {"map_key": "24:4", "x": 1, "y": 8},
        "to_map": "24:3",
        "to_pos": {"x": 10, "y": 12},
    }
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POKEMON_MEMORY_DIR", tmp)
        state = memory_node(state)
    assert any(entry.get("id") == NEW_BARK_WEST_EXIT_ID for entry in state.get("known_landmarks", []))


def test_navigation_without_landmark_uses_north_bias_on_route_29():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    target = _navigation_target(gs, state=state)
    assert target[1] < gs.player.y


def test_navigation_uses_route_29_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["known_landmarks"] = [
        make_landmark(
            landmark_id=ROUTE_29_NORTH_GATE_ID,
            name="Route 29 north gate",
            map_key="24:3",
            x=10,
            y=5,
            kind="map_visit",
        )
    ]
    assert _navigation_target(gs, state=state) == (10, 5)


def test_exploration_hint_targets_lab_warp():
    gs = GameState(player={"map_group": 24, "map_id": 4, "x": 13, "y": 6})
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    assert (
        exploration_target(gs, state, hint_tile=(6, 3))
        == (6, 3)
    )