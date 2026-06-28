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

# Secondary lab door on New Bark Town (see starter_quest.NEW_BARK_LAB_WARP).
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
    from src.graph.phases import starter_quest
    from src.state.gold_state_reader import MAP_KEY_NEW_BARK_TOWN

    if map_key != MAP_KEY_NEW_BARK_TOWN or x is None or y is None:
        return map_key, x, y
    if y == 4 and x in (5, 6, 7):
        door = starter_quest.NEW_BARK_LAB_WARP if x >= 6 else _ELMS_LAB_ALT_DOOR
        return map_key, door[0], door[1]
    if y == 3 and x == 7:
        return map_key, starter_quest.NEW_BARK_LAB_WARP[0], starter_quest.NEW_BARK_LAB_WARP[1]
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
