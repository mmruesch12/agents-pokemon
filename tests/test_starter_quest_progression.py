"""Progressive starter-quest integration via shipped nodes + StarterQuestEmulator."""

from __future__ import annotations

from src.graph.nodes import (
    apply_action_node,
    critic_node,
    interactor_node,
    memory_node,
    navigator_node,
    planner_node,
    supervisor_node,
)
from src.graph.phases import starter_quest
from src.graph.state import initial_agent_state, update_game_state
from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
    MAP_KEY_ROUTE_30,
)
from src.state.gold_state_reader import (
    ADDR_BATTLE_MODE,
    ADDR_MAP_GROUP,
    ADDR_MAP_NUMBER,
    ADDR_PARTY_COUNT,
    ADDR_X_COORD,
    ADDR_Y_COORD,
)
from src.state.models import BattlePhase, GameState
from tests.fake_emulator import StarterQuestEmulator


def _post_house_gs() -> GameState:
    return GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": False},
        party_count=0,
    )


def _post_house_memory() -> dict[int, int]:
    return {
        ADDR_MAP_GROUP: 24,
        ADDR_MAP_NUMBER: 4,
        ADDR_X_COORD: 13,
        ADDR_Y_COORD: 6,
        ADDR_PARTY_COUNT: 0,
        ADDR_BATTLE_MODE: 0,
    }


def _dispatch_specialist(state: dict) -> dict:
    node = state.get("next_node", "supervisor")
    if node == "navigator":
        return navigator_node(state)
    if node == "interactor":
        return interactor_node(state)
    if node == "planner":
        return planner_node(state)
    if node == "waiter":
        from src.graph.nodes import waiter_node

        return waiter_node(state)
    if node == "idle":
        from src.graph.nodes import idle_node

        return idle_node(state)
    if node == "battler":
        from src.graph.nodes import battler_node

        return battler_node(state)
    return state


def _macro_step(state: dict, emu: StarterQuestEmulator) -> dict:
    state = supervisor_node(state)
    state = _dispatch_specialist(state)
    state = apply_action_node(state, emu)
    gs = emu.get_game_state()
    state = update_game_state(state, gs)
    state = critic_node(state)
    state = memory_node(state)
    return state


def test_navigation_targets_route_maps_retired_from_phase():
    """Route 29/30 geography is learned via landmarks, not phase tables."""
    gs_route29 = GameState(
        player={"map_group": 24, "map_id": 3, "x": 10, "y": 12},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    assert starter_quest.navigation_target(gs_route29) is None

    gs_route30 = GameState(
        player={"map_group": 26, "map_id": 1, "x": 10, "y": 8},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    assert starter_quest.navigation_target(gs_route30) is None


def test_post_starter_new_bark_east_exit_frontier_without_landmark():
    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    from src.graph.nodes import _navigation_target

    state = {"house_exit_complete": True, "known_landmarks": []}
    assert starter_quest.navigation_target(gs) is None
    target = _navigation_target(gs, state=state)
    assert target != (gs.player.x, gs.player.y)


def test_post_starter_new_bark_uses_east_exit_landmark():
    from src.graph.nodes import _navigation_target
    from src.memory.landmarks import NEW_BARK_EAST_EXIT_ID, make_landmark

    gs = GameState(
        player={"map_group": 24, "map_id": 4, "x": 13, "y": 6},
        raw_metadata={"has_starter": True},
        party_count=1,
    )
    state = {
        "house_exit_complete": True,
        "known_landmarks": [
            make_landmark(
                landmark_id=NEW_BARK_EAST_EXIT_ID,
                name="New Bark east exit",
                map_key="24:4",
                x=19,
                y=12,
                kind="map_visit",
            )
        ],
    }
    assert _navigation_target(gs, state=state) == (19, 12)


def test_shipped_nodes_progress_post_house_to_rival_battle():
    """Full node chain + apply_action drives quest flags/maps to rival trainer battle."""
    gs = _post_house_gs()
    emu = StarterQuestEmulator(_post_house_memory())
    from src.memory.landmarks import seed_static_map_landmarks

    state = initial_agent_state(gs)
    state["bootstrap_complete"] = True
    state["house_exit_complete"] = True
    state["maps_visited"] = [MAP_KEY_NEW_BARK_TOWN]
    seed_static_map_landmarks(state)

    milestones_seen: set[str] = set()
    map_keys_seen: set[str] = set()

    for _ in range(800):
        state = _macro_step(state, emu)
        gs = GameState.model_validate(state["game_state"])
        map_keys_seen.add(gs.map_key)
        milestones_seen.update(state.get("milestones", []))
        if starter_quest.MILESTONE_RIVAL_BATTLE in milestones_seen:
            break
        if state.get("starter_quest_complete"):
            break

    gs_final = GameState.model_validate(state["game_state"])
    assert starter_quest.MILESTONE_ENTERED_LAB in milestones_seen
    assert starter_quest.MILESTONE_CHOSE_STARTER in milestones_seen
    assert starter_quest.MILESTONE_MR_POKEMON in milestones_seen
    assert MAP_KEY_ELMS_LAB in map_keys_seen
    assert MAP_KEY_ROUTE_29 in map_keys_seen
    assert MAP_KEY_ROUTE_30 in map_keys_seen
    assert MAP_KEY_MR_POKEMONS_HOUSE in map_keys_seen
    assert gs_final.raw_metadata.get("has_mystery_egg") is True


def test_memory_node_rival_milestone_from_constructed_lab_battle(battle_ram: dict):
    """Verification plan step 2: synthetic lab + trainer battle emits rival milestone."""
    from src.state.gold_state_reader import ADDR_EVENT_FLAGS, ByteArrayReader, GoldStateReader
    from src.state.script_constants import EVENT_GAVE_MYSTERY_EGG_TO_ELM

    from src.state.gold_state_reader import ADDR_BATTLE_MODE

    mem = dict(battle_ram)
    mem[ADDR_BATTLE_MODE] = 2
    mem[ADDR_EVENT_FLAGS + (EVENT_GAVE_MYSTERY_EGG_TO_ELM // 8)] = 1 << (
        EVENT_GAVE_MYSTERY_EGG_TO_ELM % 8
    )
    gs = GoldStateReader(ByteArrayReader(mem)).read()
    gs = gs.model_copy(
        update={
            "player": gs.player.model_copy(update={"map_group": 24, "map_id": 5, "x": 4, "y": 2}),
            "battle": gs.battle.model_copy(update={"in_battle": True, "phase": BattlePhase.TRAINER}),
        }
    )
    state = initial_agent_state(gs)
    state["house_exit_complete"] = True
    state["maps_visited"] = [MAP_KEY_NEW_BARK_TOWN, MAP_KEY_ELMS_LAB]

    state = memory_node(state)
    assert starter_quest.MILESTONE_RIVAL_BATTLE in state["milestones"]
    assert state["starter_quest_complete"] is True
    assert starter_quest.is_satisfied(gs, state) is True