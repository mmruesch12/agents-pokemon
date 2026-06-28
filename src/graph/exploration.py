"""Frontier exploration when landmark targets are unknown."""
from __future__ import annotations
import heapq
from typing import Any
from src.graph.pathfinding import MAP_GRIDS, _is_walkable, find_path
from src.state.models import GameState

def exploration_hint_text(state: dict[str, Any], gs: GameState) -> str:
    hints = [str(state.get("active_subgoal", "")), *state.get("subgoals", []), *state.get("current_plan", [])]
    if state.get("house_exit_complete"):
        from src.graph.phases import starter_quest
        quest = starter_quest.decompose_subgoals(gs)
        if quest: hints.extend(quest)
    return " ".join(hints)

def exploration_hint_tile(state: dict[str, Any], gs: GameState):
    if not state.get("house_exit_complete"): return None
    from src.graph.phases import starter_quest
    from src.memory.landmarks import ELMS_LAB_ENTRANCE_ID, landmark_known
    if not starter_quest.in_starter_quest(gs, state): return None
    text = exploration_hint_text(state, gs).lower()
    landmarks = list(state.get("known_landmarks", []))
    if gs.map_key == "24:4" and not landmark_known(landmarks, ELMS_LAB_ENTRANCE_ID):
        if "lab" in text or "elm" in text or "starter" in text: return starter_quest.NEW_BARK_LAB_WARP
    return None

def _subgoal_exploration_bias(text: str):
    text = text.lower()
    if "lab" in text or "elm" in text: return (0, 0)
    return None

def exploration_target(gs: GameState, state: dict[str, Any] | None = None, *, hint_tile=None):
    state = state or {}
    hint_tile = hint_tile or exploration_hint_tile(state, gs)
    if hint_tile is not None:
        path = find_path(gs.player.x, gs.player.y, hint_tile[0], hint_tile[1], map_key=gs.map_key)
        if path or (gs.player.x, gs.player.y) != hint_tile: return hint_tile
    visited = {k for k in state.get("visited_positions", []) if k.startswith(f"{gs.map_key}:")}
    grid = MAP_GRIDS.get(gs.map_key)
    bias = _subgoal_exploration_bias(exploration_hint_text(state, gs))
    start = (gs.player.x, gs.player.y)
    open_set = [(0, gs.player.x, gs.player.y, 0)]
    visited_search = {start}
    best_unvisited, best_score = None, float("-inf")
    while open_set:
        _, x, y, dist = heapq.heappop(open_set)
        pos_key = f"{gs.map_key}:{x}:{y}"
        if pos_key not in visited and (x, y) != start:
            score = -(abs(bias[0]-x)+abs(bias[1]-y)+dist*0.01) if bias else dist
            if score > best_score: best_score, best_unvisited = score, (x, y)
        for dx, dy in ((0,-1),(0,1),(-1,0),(1,0)):
            nx, ny = x+dx, y+dy
            if (nx,ny) in visited_search or not _is_walkable(grid, nx, ny): continue
            visited_search.add((nx,ny)); heapq.heappush(open_set, (dist+1, nx, ny, dist+1))
    return best_unvisited if best_unvisited else (gs.player.x+1, gs.player.y)

def gated_phase_target(gs, phase_target, *, state=None, landmark_id=None):
    from src.memory.landmarks import find_landmark, landmark_coords
    state = state or {}
    landmarks = list(state.get("known_landmarks", []))
    if landmark_id:
        landmark = find_landmark(landmarks, landmark_id=landmark_id)
        if landmark is not None and landmark.get("map_key") == gs.map_key:
            return landmark_coords(landmark)
        return exploration_target(gs, state)
    return phase_target
