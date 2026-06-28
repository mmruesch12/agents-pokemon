#!/usr/bin/env python3
"""Apply landmark navigation wiring to graph nodes, state, llm, and runner."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_state() -> None:
    path = ROOT / "src/graph/state.py"
    text = path.read_text()
    if "known_landmarks" in text:
        return
    text = text.replace(
        "    long_term_facts: list[str]\n    phase: str",
        "    long_term_facts: list[str]\n    known_landmarks: list[dict[str, Any]]\n    last_map_transition: dict[str, Any]\n    phase: str",
    )
    text = text.replace(
        "        long_term_facts=[],\n        phase=",
        "        long_term_facts=[],\n        known_landmarks=[],\n        last_map_transition={},\n        phase=",
    )
    path.write_text(text)


def patch_llm() -> None:
    path = ROOT / "src/graph/llm.py"
    if "format_landmarks_for_prompt" in path.read_text():
        return
    text = path.read_text()
    text = text.replace(
        "from src.graph.state import AgentState\nfrom src.state.models import GameState",
        "from src.graph.state import AgentState\nfrom src.memory.landmarks import format_landmarks_for_prompt\nfrom src.state.models import GameState",
    )
    text = text.replace(
        "def llm_plan(gs: GameState, state: AgentState) -> dict[str, Any] | None:",
        "def llm_plan(gs: GameState, state: AgentState, landmarks: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:",
    )
    text = text.replace(
        '        f"Battle: {gs.battle.in_battle}\\n"\n        f"Current map only',
        '        f"Battle: {gs.battle.in_battle}\\n"\n    )\n    landmark_text = format_landmarks_for_prompt(landmarks or [])\n    prompt = (\n        f"Map: {gs.player.map_name} ({gs.map_key}) at ({gs.player.x},{gs.player.y})\\n"\n        f"Party: {gs.party_count}, Badges: {gs.total_badges}\\n"\n        f"Battle: {gs.battle.in_battle}\\n"\n    )\n    if landmark_text:\n        prompt += f"{landmark_text}\\n"\n    prompt += (\n        f"Current map only',
    )
    text = text.replace(
        "def llm_navigate(gs: GameState, state: AgentState, candidates: list[str]) -> str | None:",
        "def llm_navigate(gs: GameState, state: AgentState, candidates: list[str], landmarks: list[dict[str, Any]] | None = None, *, target: tuple[int, int] | None = None) -> str | None:",
    )
    old_nav_prompt = '''    prompt = (
        f"Map: {gs.player.map_name} at ({gs.player.x},{gs.player.y})\\n"
        f"Subgoal: {state.get('active_subgoal', '')}\\n"
        f"Visited count: {len(state.get('visited_positions', []))}\\n"
        f"Choose ONE direction from: {', '.join(candidates)}\\n"
        "Reply with only the direction word."
    )'''
    new_nav_prompt = '''    landmark_text = format_landmarks_for_prompt(landmarks or [])
    prompt = (
        f"Map: {gs.player.map_name} ({gs.map_key}) at ({gs.player.x},{gs.player.y})\\n"
        f"Subgoal: {state.get('active_subgoal', '')}\\n"
        f"Party: {gs.party_count} | In dialog: {gs.in_text_box}\\n"
        f"Visited count: {len(state.get('visited_positions', []))}\\n"
    )
    if landmark_text:
        prompt += f"{landmark_text}\\n"
    elif target:
        prompt += f"Navigation target tile: ({target[0]},{target[1]})\\n"
    else:
        prompt += "No known landmarks yet — explore to discover locations.\\n"
    prompt += (
        f"Valid next path steps (pick one): {', '.join(candidates)}\\n"
        "Reply with only the direction word."
    )'''
    text = text.replace(old_nav_prompt, new_nav_prompt)
    path.write_text(text)


def patch_runner() -> None:
    path = ROOT / "src/run/autonomous_runner.py"
    text = path.read_text()
    if "hydrate_state" in text:
        return
    text = text.replace(
        "                    state = self._bootstrap_if_needed(emu, state)\n\n                start_steps",
        "                    state = self._bootstrap_if_needed(emu, state)\n\n                state = self.memory.hydrate_state(state)\n\n                start_steps",
    )
    text = text.replace(
        '                            self.memory.add_fact(f"milestone:{m}")\n\n                    if state.get("stuck_count"',
        '                            self.memory.add_fact(f"milestone:{m}")\n\n                    if state.get("known_landmarks"):\n                        self.memory.sync_landmarks_from_state(state)\n\n                    if state.get("stuck_count"',
    )
    path.write_text(text)


def patch_nodes() -> None:
    path = ROOT / "src/graph/nodes.py"
    text = path.read_text()
    if "landmark_known" in text:
        return

    old_import = '''from src.emulator.bootstrap import needs_bootstrap, pick_bootstrap_button
from src.graph.llm import llm_battle, llm_navigate, llm_plan
from src.graph.pathfinding import direction_toward, find_path
from src.graph.phases import house_exit, starter_quest
from src.graph.state import AgentState, update_game_state
from src.state.gold_state_reader import (
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    MAP_KEY_ROUTE_29,
    PLAYERS_HOUSE_1F_DOOR,
)'''
    new_import = '''from src.emulator.bootstrap import needs_bootstrap, pick_bootstrap_button
from src.graph.exploration import exploration_target, gated_phase_target
from src.graph.llm import llm_battle, llm_navigate, llm_plan
from src.graph.pathfinding import direction_toward, find_path
from src.graph.phases import house_exit, starter_quest
from src.graph.state import AgentState, update_game_state
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_INTERIOR_ID,
    apply_landmark_discovery,
    discover_elms_lab_landmarks,
    discover_map_visit_landmark,
    format_landmarks_for_prompt,
    landmark_known,
    memory_data_dir,
    parse_position_key,
    retrieve_landmarks_from_state,
)
from src.memory.long_term_memory import LongTermMemory
from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_PLAYERS_HOUSE_1F,
    MAP_KEY_PLAYERS_HOUSE_2F,
    MAP_KEY_ROUTE_29,
    PLAYERS_HOUSE_1F_DOOR,
)'''
    text = text.replace(old_import, new_import)

    helpers = '''
_LANDMARK_GATED_INTERIOR_TARGETS = frozenset(
    {starter_quest.STARTER_BALL_TILE, starter_quest.ELM_DESK_TILE}
)
_LAB_DOOR_TILES = frozenset({starter_quest.NEW_BARK_LAB_WARP, (5, 3)})


def _long_term_memory() -> LongTermMemory:
    return LongTermMemory(data_dir=memory_data_dir())


def _attach_landmark_context(state: AgentState, gs: GameState) -> list[dict[str, Any]]:
    landmarks = list(state.get("known_landmarks", []))
    query = f"{gs.map_key} {gs.player.map_name} {state.get('active_subgoal', '')}"
    relevant = retrieve_landmarks_from_state(landmarks, query, k=3)
    formatted = format_landmarks_for_prompt(relevant)
    if formatted:
        retrievals = list(state.get("memory_retrievals", []))
        if formatted not in retrievals:
            retrievals.append(formatted)
        state["memory_retrievals"] = retrievals[-5:]
    return relevant


def _gate_starter_quest_target(
    gs: GameState,
    quest_target: tuple[int, int],
    *,
    state: AgentState | None = None,
) -> tuple[int, int]:
    state = state or {}
    landmarks = list(state.get("known_landmarks", []))
    if quest_target == starter_quest.NEW_BARK_LAB_WARP:
        if landmark_known(landmarks, ELMS_LAB_ENTRANCE_ID):
            return gated_phase_target(
                gs, quest_target, state=state, landmark_id=ELMS_LAB_ENTRANCE_ID
            )
        return exploration_target(gs, state, hint_tile=starter_quest.NEW_BARK_LAB_WARP)
    if quest_target in _LANDMARK_GATED_INTERIOR_TARGETS:
        if landmark_known(landmarks, ELMS_LAB_INTERIOR_ID):
            return quest_target
        return exploration_target(gs, state)
    return quest_target


def _lab_door_interact_candidate(gs: GameState, state: AgentState | None = None) -> bool:
    state = state or {}
    if gs.map_key != MAP_KEY_NEW_BARK_TOWN:
        return False
    if landmark_known(state.get("known_landmarks", []), ELMS_LAB_INTERIOR_ID):
        return False
    return (gs.player.x, gs.player.y) in _LAB_DOOR_TILES


def _persist_landmark_discoveries(state: AgentState, discoveries: list[dict[str, Any]]) -> None:
    if not discoveries:
        return
    apply_landmark_discovery(state, discoveries)
    try:
        memory = _long_term_memory()
        for landmark in discoveries:
            memory.add_landmark(landmark)
            logger.info(
                "Landmark discovered: %s at %s (%s,%s)",
                landmark.get("name"),
                landmark.get("map_key"),
                landmark.get("x"),
                landmark.get("y"),
            )
    except OSError as exc:
        logger.warning("Could not persist landmarks: %s", exc)


'''
    text = text.replace("EARLY_GAME_OBJECTIVES = {", helpers + "EARLY_GAME_OBJECTIVES = {")
    text = text.replace(
        "    map_key = gs.map_key\n\n    objective = EARLY_GAME_OBJECTIVES.get(map_key, \"Explore and progress story\")",
        "    map_key = gs.map_key\n    relevant_landmarks = _attach_landmark_context(state, gs)\n\n    objective = EARLY_GAME_OBJECTIVES.get(map_key, \"Explore and progress story\")",
    )
    text = text.replace("        llm_result = llm_plan(gs, state)", "        llm_result = llm_plan(gs, state, relevant_landmarks)")
    text = text.replace(
        "    target = _navigation_target(gs, map_key=map_key, state=state)\n    path = find_path(gs.player.x, gs.player.y, target[0], target[1], map_key=map_key)\n    candidates = _navigation_candidates(gs, target, path, state)\n\n    door_exit = _players_house_door_exit(gs)\n    if door_exit:\n        action = door_exit\n    else:\n        llm_choice = llm_navigate(gs, state, candidates)",
        "    relevant_landmarks = _attach_landmark_context(state, gs)\n    target = _navigation_target(gs, map_key=map_key, state=state)\n    path = find_path(gs.player.x, gs.player.y, target[0], target[1], map_key=map_key)\n    candidates = _navigation_candidates(gs, target, path, state)\n\n    door_exit = _players_house_door_exit(gs)\n    if door_exit:\n        action = door_exit\n    else:\n        llm_choice = llm_navigate(\n            gs, state, candidates, relevant_landmarks, target=target\n        )",
    )
    text = text.replace(
        "    if house_exit.prefer_interact_candidate(gs) or starter_quest.prefer_interact_candidate(gs):\n        candidates.insert(0, \"a\")",
        "    if (\n        house_exit.prefer_interact_candidate(gs)\n        or starter_quest.prefer_interact_candidate(gs)\n        or _lab_door_interact_candidate(gs, state)\n    ):\n        candidates.insert(0, \"a\")",
    )
    text = text.replace(
        "        if quest_target is not None:\n            return quest_target",
        "        if quest_target is not None:\n            return _gate_starter_quest_target(gs, quest_target, state=state)",
    )
    old_mem = '''    if gs.map_key not in maps_visited:
        maps_visited.append(gs.map_key)
    state["maps_visited"] = maps_visited

    milestone = _check_milestone(gs, state, maps_visited)
    if milestone and milestone not in milestones:
        milestones.append(milestone)
        logger.info("Milestone: %s", milestone)
        if milestone == house_exit.HOUSE_EXIT_MILESTONE:
            house_exit.on_house_exit_complete(state, gs)
        elif milestone == starter_quest.MILESTONE_RIVAL_BATTLE:
            starter_quest.on_starter_quest_complete(state, gs)

    state["milestones"] = milestones'''
    new_mem = '''    discoveries: list[dict[str, Any]] = []
    if gs.map_key not in maps_visited:
        maps_visited.append(gs.map_key)
        discoveries.append(discover_map_visit_landmark(gs))
    state["maps_visited"] = maps_visited

    transition = state.get("last_map_transition") or {}
    if (
        transition.get("to_map") == MAP_KEY_ELMS_LAB
        and not landmark_known(state.get("known_landmarks", []), ELMS_LAB_INTERIOR_ID)
    ):
        entrance = transition.get("from_pos") or {}
        discoveries.extend(
            discover_elms_lab_landmarks(
                gs,
                entrance_map_key=entrance.get("map_key"),
                entrance_x=entrance.get("x"),
                entrance_y=entrance.get("y"),
            )
        )
        state["last_map_transition"] = {}

    milestone = _check_milestone(gs, state, maps_visited)
    if milestone and milestone not in milestones:
        milestones.append(milestone)
        logger.info("Milestone: %s", milestone)
        if milestone == house_exit.HOUSE_EXIT_MILESTONE:
            house_exit.on_house_exit_complete(state, gs)
        elif milestone == starter_quest.MILESTONE_RIVAL_BATTLE:
            starter_quest.on_starter_quest_complete(state, gs)

    if milestone == starter_quest.MILESTONE_ENTERED_LAB and not landmark_known(
        state.get("known_landmarks", []), ELMS_LAB_INTERIOR_ID
    ):
        discoveries.extend(discover_elms_lab_landmarks(gs))

    if discoveries:
        _persist_landmark_discoveries(state, discoveries)

    state["milestones"] = milestones'''
    text = text.replace(old_mem, new_mem)
    text = text.replace(
        "        house_exit.on_map_change(map_before, gs, state, action=action)\n        starter_quest.on_map_change(map_before, gs, state, action=action)",
        "        if map_before != gs.map_key:\n            parsed = parse_position_key(pos_before)\n            if parsed is not None:\n                from_map, from_x, from_y = parsed\n                state[\"last_map_transition\"] = {\n                    \"from_map\": from_map,\n                    \"from_pos\": {\"map_key\": from_map, \"x\": from_x, \"y\": from_y},\n                    \"to_map\": gs.map_key,\n                    \"to_pos\": {\"x\": gs.player.x, \"y\": gs.player.y},\n                }\n        house_exit.on_map_change(map_before, gs, state, action=action)\n        starter_quest.on_map_change(map_before, gs, state, action=action)",
    )
    path.write_text(text)


def main() -> None:
    import subprocess

    for rel in (
        "src/memory/landmarks.py",
        "src/memory/long_term_memory.py",
        "src/graph/exploration.py",
    ):
        dest = ROOT / rel
        if not dest.exists():
            subprocess.run(
                ["git", "show", f"1462f09:{rel}"],
                cwd=ROOT,
                check=True,
                stdout=open(dest, "w"),
            )
    patch_state()
    patch_llm()
    patch_runner()
    patch_nodes()
    print("landmark wiring applied")


if __name__ == "__main__":
    main()