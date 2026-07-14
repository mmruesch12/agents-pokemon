"""Landmark discovery, retrieval, and formatting helpers."""

from __future__ import annotations

import os
from typing import Any

from src.state.models import GameState

LANDMARK_KIND_MAP_VISIT = "map_visit"
LANDMARK_KIND_BUILDING_ENTRANCE = "building_entrance"
LANDMARK_KIND_INTERIOR = "interior"

ELMS_LAB_ENTRANCE_ID = "elms_lab_entrance"
ELMS_LAB_INTERIOR_ID = "elms_lab_interior"
ELMS_LAB_DESK_APPROACH_ID = "elms_lab_desk_approach"
ELMS_LAB_BALL_APPROACH_ID = "elms_lab_ball_approach"
ELMS_LAB_EXIT_ID = "elms_lab_exit"
NEW_BARK_WEST_EXIT_ID = "new_bark_west_exit"
# Deprecated alias — Route 29 is west of New Bark, not east.
NEW_BARK_EAST_EXIT_ID = NEW_BARK_WEST_EXIT_ID
ROUTE_29_NORTH_GATE_ID = "route_29_north_gate"
ROUTE_30_NORTH_GATE_ID = "route_30_north_gate"
ROUTE_30_TO_ROUTE_31_ID = "route_30_to_route_31"
CHERRYGROVE_NORTH_EXIT_ID = "cherrygrove_north_exit"
ROUTE_31_WEST_GATE_ID = "route_31_west_gate"
VIOLET_GYM_ENTRANCE_ID = "violet_gym_entrance"
MR_POKEMONS_HOUSE_ENTRANCE_ID = "mr_pokemons_house_entrance"

# Lab door tiles on New Bark Town (discovered via map transitions, not phase routing).
_ELMS_LAB_PRIMARY_DOOR = (6, 3)
_ELMS_LAB_ALT_DOOR = (5, 3)


def memory_data_dir() -> str:
    return os.getenv("POKEMON_MEMORY_DIR", "data/memory")


def parse_position_key(position_key: str) -> tuple[str, int, int] | None:
    parts = position_key.split(":")
    if len(parts) != 4:
        return None
    try:
        return f"{parts[0]}:{parts[1]}", int(parts[2]), int(parts[3])
    except ValueError:
        return None


def landmark_coords(landmark: dict[str, Any]) -> tuple[int, int]:
    return int(landmark["x"]), int(landmark["y"])


def make_landmark(
    *,
    landmark_id: str,
    name: str,
    map_key: str,
    x: int,
    y: int,
    kind: str = LANDMARK_KIND_MAP_VISIT,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": landmark_id,
        "name": name,
        "map_key": map_key,
        "x": x,
        "y": y,
        "kind": kind,
        "metadata": metadata or {},
    }


def find_landmark(landmarks: list[dict[str, Any]], *, landmark_id: str | None = None) -> dict[str, Any] | None:
    if not landmark_id:
        return None
    for entry in landmarks:
        if entry.get("id") == landmark_id:
            return entry
    return None


def landmark_known(landmarks: list[dict[str, Any]], landmark_id: str) -> bool:
    return find_landmark(landmarks, landmark_id=landmark_id) is not None


def merge_landmark(landmarks: list[dict[str, Any]], landmark: dict[str, Any]) -> list[dict[str, Any]]:
    landmark_id = landmark.get("id")
    if not landmark_id:
        return landmarks
    merged = [entry for entry in landmarks if entry.get("id") != landmark_id]
    merged.append(landmark)
    return merged


def retrieve_landmarks_from_state(landmarks: list[dict[str, Any]], query: str, *, k: int = 3) -> list[dict[str, Any]]:
    query_lower = query.lower()
    tokens = [token for token in query_lower.split() if token]
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in landmarks:
        haystack = " ".join([str(entry.get("id", "")), str(entry.get("name", "")), str(entry.get("map_key", "")), str(entry.get("kind", ""))]).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].get("name", "")))
    if scored:
        return [entry for _, entry in scored[:k]]
    return landmarks[-k:]


def format_landmarks_for_prompt(landmarks: list[dict[str, Any]]) -> str:
    if not landmarks:
        return ""
    lines = [f"{entry.get('name', 'Landmark')} at {entry.get('map_key')} ({entry.get('x')},{entry.get('y')})" for entry in landmarks]
    return "Known landmarks: " + "; ".join(lines)


def discover_map_visit_landmark(gs: GameState) -> dict[str, Any]:
    return make_landmark(
        landmark_id=f"map:{gs.map_key}",
        name=gs.player.map_name or f"Map {gs.map_key}",
        map_key=gs.map_key,
        x=gs.player.x,
        y=gs.player.y,
        kind=LANDMARK_KIND_MAP_VISIT,
        metadata={"discovered_on_first_visit": True},
    )


def normalize_elms_lab_entrance_coords(
    map_key: str | None,
    x: int | None,
    y: int | None,
) -> tuple[str | None, int | None, int | None]:
    """Snap pre-warp positions adjacent to the lab door to the actual door tile."""
    from src.state.gold_state_reader import MAP_KEY_NEW_BARK_TOWN

    if map_key != MAP_KEY_NEW_BARK_TOWN or x is None or y is None:
        return map_key, x, y
    if y == 4 and x in (5, 6, 7):
        door = _ELMS_LAB_PRIMARY_DOOR if x >= 6 else _ELMS_LAB_ALT_DOOR
        return map_key, door[0], door[1]
    if y == 3 and x == 7:
        return map_key, _ELMS_LAB_PRIMARY_DOOR[0], _ELMS_LAB_PRIMARY_DOOR[1]
    return map_key, x, y


def discover_elms_lab_landmarks(gs: GameState, *, entrance_map_key: str | None = None, entrance_x: int | None = None, entrance_y: int | None = None) -> list[dict[str, Any]]:
    landmarks: list[dict[str, Any]] = []
    if entrance_map_key is not None and entrance_x is not None and entrance_y is not None:
        entrance_map_key, entrance_x, entrance_y = normalize_elms_lab_entrance_coords(
            entrance_map_key, entrance_x, entrance_y
        )
        landmarks.append(make_landmark(landmark_id=ELMS_LAB_ENTRANCE_ID, name="Elm's Lab entrance", map_key=entrance_map_key, x=entrance_x, y=entrance_y, kind=LANDMARK_KIND_BUILDING_ENTRANCE, metadata={"building": "elms_lab"}))
    landmarks.append(make_landmark(landmark_id=ELMS_LAB_INTERIOR_ID, name="Elm's Lab", map_key=gs.map_key, x=gs.player.x, y=gs.player.y, kind=LANDMARK_KIND_INTERIOR, metadata={"building": "elms_lab"}))
    return landmarks


def discover_quest_transition_landmarks(
    *,
    from_map: str | None,
    to_map: str | None,
    from_pos: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Record warp tiles discovered on first Route 29 / route / Mr. Pokemon transitions."""
    from src.state.gold_state_reader import (
        MAP_KEY_CHERRYGROVE_CITY,
        MAP_KEY_MR_POKEMONS_HOUSE,
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
        MAP_KEY_ROUTE_31,
        MAP_KEY_VIOLET_CITY,
        MAP_KEY_VIOLET_GYM,
    )

    if not from_map or not to_map or not from_pos:
        return []
    map_key = from_pos.get("map_key")
    x = from_pos.get("x")
    y = from_pos.get("y")
    if map_key is None or x is None or y is None:
        return []

    landmarks: list[dict[str, Any]] = []
    if from_map == MAP_KEY_NEW_BARK_TOWN and to_map == MAP_KEY_ROUTE_29:
        landmarks.append(
            make_landmark(
                landmark_id=NEW_BARK_WEST_EXIT_ID,
                name="New Bark Route 29 exit",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_MAP_VISIT,
                metadata={"transition": "new_bark_to_route_29"},
            )
        )
    elif from_map == MAP_KEY_ROUTE_29 and to_map == MAP_KEY_ROUTE_30:
        landmarks.append(
            make_landmark(
                landmark_id=ROUTE_29_NORTH_GATE_ID,
                name="Route 29 north gate",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_MAP_VISIT,
                metadata={"transition": "route_29_to_route_30"},
            )
        )
    elif from_map == MAP_KEY_ROUTE_30 and to_map == MAP_KEY_MR_POKEMONS_HOUSE:
        landmarks.append(
            make_landmark(
                landmark_id=ROUTE_30_NORTH_GATE_ID,
                name="Route 30 north approach",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_MAP_VISIT,
                metadata={"transition": "route_30_to_mr_pokemon"},
            )
        )
    elif from_map == MAP_KEY_ROUTE_30 and to_map == MAP_KEY_ROUTE_31:
        landmarks.append(
            make_landmark(
                landmark_id=ROUTE_30_TO_ROUTE_31_ID,
                name="Route 30 to Route 31",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_MAP_VISIT,
                metadata={"transition": "route_30_to_route_31"},
            )
        )
    elif from_map == MAP_KEY_CHERRYGROVE_CITY and to_map == MAP_KEY_ROUTE_30:
        landmarks.append(
            make_landmark(
                landmark_id=CHERRYGROVE_NORTH_EXIT_ID,
                name="Cherrygrove north exit",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_MAP_VISIT,
                metadata={"transition": "cherrygrove_to_route_30"},
            )
        )
    elif from_map == MAP_KEY_ROUTE_31 and to_map in (
        MAP_KEY_VIOLET_CITY,
        "26:11",
    ):
        landmarks.append(
            make_landmark(
                landmark_id=ROUTE_31_WEST_GATE_ID,
                name="Route 31 west toward Violet",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_MAP_VISIT,
                metadata={"transition": "route_31_to_violet"},
            )
        )
    elif from_map == MAP_KEY_VIOLET_CITY and to_map == MAP_KEY_VIOLET_GYM:
        landmarks.append(
            make_landmark(
                landmark_id=VIOLET_GYM_ENTRANCE_ID,
                name="Violet Gym entrance",
                map_key=map_key,
                x=int(x),
                y=int(y),
                kind=LANDMARK_KIND_BUILDING_ENTRANCE,
                metadata={"transition": "violet_to_gym", "building": "violet_gym"},
            )
        )
    return landmarks


def discover_mr_pokemon_entrance_landmark(gs: GameState) -> dict[str, Any]:
    """Record the interior door tile on first Mr. Pokemon's House visit."""
    from src.state.gold_state_reader import MAP_KEY_MR_POKEMONS_HOUSE

    door = (5, 5)
    return make_landmark(
        landmark_id=MR_POKEMONS_HOUSE_ENTRANCE_ID,
        name="Mr. Pokemon's House entrance",
        map_key=MAP_KEY_MR_POKEMONS_HOUSE,
        x=door[0],
        y=door[1],
        kind=LANDMARK_KIND_BUILDING_ENTRANCE,
        metadata={"building": "mr_pokemon", "discovered_on_first_visit": True},
    )


def seed_static_map_landmarks(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Register known building entrances and warp gates from MAP_LANDMARK_ANCHORS."""
    from src.graph.pathfinding import MAP_LANDMARK_ANCHORS, MAP_WARP_HINT_ROWS
    from src.state.gold_state_reader import (
        MAP_KEY_CHERRYGROVE_CITY,
        MAP_KEY_ELMS_LAB,
        MAP_KEY_NEW_BARK_TOWN,
        MAP_KEY_ROUTE_29,
        MAP_KEY_ROUTE_30,
        MAP_KEY_ROUTE_31,
        MAP_KEY_VIOLET_CITY,
    )

    merged = list(state.get("known_landmarks", []))
    new_bark = MAP_LANDMARK_ANCHORS.get(MAP_KEY_NEW_BARK_TOWN, {})
    route_29 = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {})
    route_30 = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_30, {})
    cherry = MAP_LANDMARK_ANCHORS.get(MAP_KEY_CHERRYGROVE_CITY, {})
    route_31 = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_31, {})
    violet = MAP_LANDMARK_ANCHORS.get(MAP_KEY_VIOLET_CITY, {})
    elms_lab = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ELMS_LAB, {})
    west_row = MAP_WARP_HINT_ROWS.get(MAP_KEY_NEW_BARK_TOWN, {}).get("west", 8)
    lab_door = new_bark.get("elms_lab_door", _ELMS_LAB_PRIMARY_DOOR)
    west_exit = new_bark.get("west_exit", (1, west_row))
    static = [
        make_landmark(
            landmark_id=ELMS_LAB_ENTRANCE_ID,
            name="Elm's Lab entrance",
            map_key=MAP_KEY_NEW_BARK_TOWN,
            x=lab_door[0],
            y=lab_door[1],
            kind=LANDMARK_KIND_BUILDING_ENTRANCE,
            metadata={"building": "elms_lab", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=NEW_BARK_WEST_EXIT_ID,
            name="New Bark Route 29 exit",
            map_key=MAP_KEY_NEW_BARK_TOWN,
            x=west_exit[0],
            y=west_exit[1],
            kind=LANDMARK_KIND_MAP_VISIT,
            metadata={"transition": "new_bark_to_route_29", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=ROUTE_29_NORTH_GATE_ID,
            name="Route 29 north gate",
            map_key=MAP_KEY_ROUTE_29,
            x=route_29.get("route_30_gate", (10, 8))[0],
            y=route_29.get("route_30_gate", (10, 8))[1],
            kind=LANDMARK_KIND_MAP_VISIT,
            metadata={"transition": "route_29_to_route_30", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=ROUTE_30_NORTH_GATE_ID,
            name="Route 30 north approach",
            map_key=MAP_KEY_ROUTE_30,
            x=route_30.get("mr_pokemon_gate", (17, 5))[0],
            y=route_30.get("mr_pokemon_gate", (17, 5))[1],
            kind=LANDMARK_KIND_MAP_VISIT,
            metadata={"transition": "route_30_to_mr_pokemon", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=ROUTE_30_TO_ROUTE_31_ID,
            name="Route 30 toward Route 31",
            map_key=MAP_KEY_ROUTE_30,
            x=route_30.get("route_31_gate", (5, 0))[0],
            y=route_30.get("route_31_gate", (5, 0))[1],
            kind=LANDMARK_KIND_MAP_VISIT,
            metadata={"transition": "route_30_to_route_31", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=CHERRYGROVE_NORTH_EXIT_ID,
            name="Cherrygrove north exit",
            map_key=MAP_KEY_CHERRYGROVE_CITY,
            x=cherry.get("north_exit", (17, 0))[0],
            y=cherry.get("north_exit", (17, 0))[1],
            kind=LANDMARK_KIND_MAP_VISIT,
            metadata={"transition": "cherrygrove_to_route_30", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=ROUTE_31_WEST_GATE_ID,
            name="Route 31 west toward Violet",
            map_key=MAP_KEY_ROUTE_31,
            x=route_31.get("west_gate", (0, 8))[0],
            y=route_31.get("west_gate", (0, 8))[1],
            kind=LANDMARK_KIND_MAP_VISIT,
            metadata={"transition": "route_31_to_violet", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=VIOLET_GYM_ENTRANCE_ID,
            name="Violet Gym entrance",
            map_key=MAP_KEY_VIOLET_CITY,
            x=violet.get("gym_entrance", (18, 17))[0],
            y=violet.get("gym_entrance", (18, 17))[1],
            kind=LANDMARK_KIND_BUILDING_ENTRANCE,
            metadata={"building": "violet_gym", "seed": "map_anchors"},
        ),
        make_landmark(
            landmark_id=ELMS_LAB_DESK_APPROACH_ID,
            name="Elm's Lab desk approach",
            map_key=MAP_KEY_ELMS_LAB,
            x=elms_lab.get("desk_approach", (4, 3))[0],
            y=elms_lab.get("desk_approach", (4, 3))[1],
            kind=LANDMARK_KIND_INTERIOR,
            metadata={"building": "elms_lab", "seed": "map_anchors", "anchor": "desk"},
        ),
        make_landmark(
            landmark_id=ELMS_LAB_BALL_APPROACH_ID,
            name="Elm's Lab ball approach",
            map_key=MAP_KEY_ELMS_LAB,
            x=elms_lab.get("ball_approach", (6, 4))[0],
            y=elms_lab.get("ball_approach", (6, 4))[1],
            kind=LANDMARK_KIND_INTERIOR,
            metadata={"building": "elms_lab", "seed": "map_anchors", "anchor": "balls"},
        ),
        make_landmark(
            landmark_id=ELMS_LAB_EXIT_ID,
            name="Elm's Lab exit",
            map_key=MAP_KEY_ELMS_LAB,
            x=elms_lab.get("south_exit", (4, 11))[0],
            y=elms_lab.get("south_exit", (4, 11))[1],
            kind=LANDMARK_KIND_INTERIOR,
            metadata={"building": "elms_lab", "seed": "map_anchors", "anchor": "exit"},
        ),
    ]
    for landmark in static:
        merged = merge_landmark(merged, landmark)
    state["known_landmarks"] = merged
    return merged


def apply_landmark_discovery(state: dict[str, Any], landmarks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(state.get("known_landmarks", []))
    for landmark in landmarks:
        merged = merge_landmark(merged, landmark)
    state["known_landmarks"] = merged
    formatted = format_landmarks_for_prompt(merged)
    retrievals = list(state.get("memory_retrievals", []))
    if formatted and formatted not in retrievals:
        retrievals.append(formatted)
    state["memory_retrievals"] = retrievals[-5:]
    return merged
