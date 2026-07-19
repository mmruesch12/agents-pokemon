"""Landmark-first navigation target resolution (roadmap Phase 3)."""

from __future__ import annotations

from typing import Any

from src.graph.exploration import exploration_target
from src.graph.pathfinding import (
    MAP_LANDMARK_ANCHORS,
    find_path,
    session_walkable_for_map,
)
from src.state.gold_state_reader import (
    MAP_KEY_ELMS_LAB,
    MAP_KEY_MR_POKEMONS_HOUSE,
    MAP_KEY_NEW_BARK_TOWN,
    MAP_KEY_ROUTE_29,
)
from src.state.models import GameState
from src.memory.landmarks import (
    ELMS_LAB_ENTRANCE_ID,
    ELMS_LAB_EXIT_ID,
    ELMS_LAB_INTERIOR_ID,
    MR_POKEMONS_HOUSE_ENTRANCE_ID,
    ROUTE_29_EAST_EXIT_ID,
    ROUTE_29_WEST_EXIT_ID,
    find_landmark,
    landmark_coords,
)


def _landmark_target_on_map(
    landmarks: list[dict[str, Any]],
    landmark_id: str,
    map_key: str,
) -> tuple[int, int] | None:
    landmark = find_landmark(landmarks, landmark_id=landmark_id)
    if landmark is None or landmark.get("map_key") != map_key:
        return None
    return landmark_coords(landmark)


ROUTE_29_SOUTH_CORRIDOR: tuple[int, int] = (14, 14)
ROUTE_29_CORRIDOR_EAST_REENTRY: tuple[int, int] = (22, 14)
ROUTE_29_LEDGE_CLIMB: tuple[int, int] = (23, 11)
ROUTE_29_LEDGE_CONNECTOR: tuple[int, int] = (27, 10)
ROUTE_29_LEDGE_WEST_DESCENT: tuple[int, int] = (25, 11)
ROUTE_29_WEST_GATE_APPROACH: tuple[int, int] = (10, 8)
ROUTE_29_Y16_EAST_ANCHOR: tuple[int, int] = (24, 16)
ROUTE_29_GATE_APPROACH_X = 24
ROUTE_29_EAST_LEDGE_DEAD_END_X = 44
ROUTE_29_SIGN_DEAD_END_X = 14


def _route_29_west_corridor_waypoint(
    px: int,
    py: int,
    *,
    map_key: str,
    state: dict[str, Any] | None,
) -> tuple[int, int] | None:
    """ROM-valid west-row interim target toward the Route 30 gate column."""
    approach = ROUTE_29_WEST_GATE_APPROACH
    if find_path(px, py, approach[0], approach[1], map_key=map_key, state=state):
        return approach
    return None


def _route_29_gate_path_drifts_east(path: list[str]) -> bool:
    """True when routing would hug east instead of the south corridor or ledge-up approach."""
    if not path:
        return True
    if path[0] == "down" or (
        len(path) >= 2 and path[0] == "right" and path[1] == "down"
    ):
        return False
    east_without_west = 0
    for step in path[:12]:
        if step == "left":
            return False
        if step == "right":
            east_without_west += 1
            if east_without_west >= 3:
                return True
    return east_without_west >= 2


def _route_29_gate_south_corridor_waypoint(
    gs: GameState,
    target: tuple[int, int],
    state: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """Interim ROM-valid target before the north gate when east of the west corridor.

    Once the player reaches the west-corridor gate approach column (or is already
    west of it on the corridor rows), hand off to ``west_exit`` so pathfinding
    continues into Cherrygrove instead of thrashing on the gate tile or turning
    back east toward the gate from the map edge.
    """
    gate = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("route_30_gate")
    if gate is None or target != gate or gs.map_key != MAP_KEY_ROUTE_29:
        return target
    px, py = gs.player.x, gs.player.y
    west_exit = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ROUTE_29, {}).get("west_exit")
    # Mid-north pocket east of the ledge connector (x>27, y<=11): never send the
    # agent back to south corridor (14,14) — path[0] becomes "down" and fights
    # climb forces (live thrash at 30,10↔30,11 with stuck_count=0). Leave ledge
    # connector / west-descent tiles (x<=27) to the existing climb handoffs.
    if py <= 11 and 28 <= px <= 42:
        approach = ROUTE_29_WEST_GATE_APPROACH
        if find_path(
            px, py, approach[0], approach[1], map_key=gs.map_key, state=state
        ):
            return approach
        if west_exit is not None and find_path(
            px, py, west_exit[0], west_exit[1], map_key=gs.map_key, state=state
        ):
            return west_exit
    # At/near gate approach column on corridor rows → Cherrygrove edge.
    # Allow a few tiles east of the gate column so x=11 thrash still hands off
    # west instead of oscillating gate↔column.
    #
    # Wall at x=8 on y=6–8 blocks direct left from the gate. A* to west_exit from
    # (10,7)/(10,8) steps *east* first then south — thrash + NPC traps. Prefer the
    # open y=10 gap west of the wall, then the map edge.
    west_south_gap = (4, 10)
    if west_exit is not None and px <= gate[0] + 3 and py <= gate[1] + 2:
        if (px, py) == west_exit:
            return west_exit
        # Still east of the x=8 wall: south gap first (path is left-only once there).
        if px >= 8:
            if find_path(
                px, py, west_south_gap[0], west_south_gap[1],
                map_key=gs.map_key, state=state,
            ):
                return west_south_gap
        if find_path(
            px, py, west_exit[0], west_exit[1], map_key=gs.map_key, state=state
        ):
            return west_exit
        if find_path(
            px, py, west_south_gap[0], west_south_gap[1],
            map_key=gs.map_key, state=state,
        ):
            return west_south_gap
    reentry = ROUTE_29_CORRIDOR_EAST_REENTRY
    ledge = ROUTE_29_LEDGE_CONNECTOR
    climb = ROUTE_29_LEDGE_CLIMB
    walked = session_walkable_for_map(state, gs.map_key)
    west = ROUTE_29_LEDGE_WEST_DESCENT
    west_complete = west in walked or (
        ledge in walked and py > ledge[1]
    )
    skip_ledge_reclimb = west_complete
    if west_complete and py == 12 and px >= 23:
        west_row = _route_29_west_corridor_waypoint(
            px, py, map_key=gs.map_key, state=state
        )
        if west_row is not None:
            return west_row
    if (
        west_complete
        and py <= 12
        and px > ROUTE_29_WEST_GATE_APPROACH[0]
        and px <= ledge[0]
    ):
        approach = ROUTE_29_WEST_GATE_APPROACH
        if find_path(
            px, py, approach[0], approach[1], map_key=gs.map_key, state=state
        ):
            return approach
    if py == 11 and px >= west[0]:
        approach = ROUTE_29_WEST_GATE_APPROACH
        if find_path(
            px, py, approach[0], approach[1], map_key=gs.map_key, state=state
        ):
            return approach
    if (px, py) == west:
        return ROUTE_29_WEST_GATE_APPROACH
    if (px, py) == ledge:
        if find_path(
            px, py, west[0], west[1], map_key=gs.map_key, state=state
        ):
            return west
    if climb in walked and ledge in walked and (px, py) == (26, 10):
        if find_path(
            px, py, west[0], west[1], map_key=gs.map_key, state=state
        ):
            return west
    if py <= ledge[1] and px >= ROUTE_29_EAST_LEDGE_DEAD_END_X:
        corridor = ROUTE_29_SOUTH_CORRIDOR
        if find_path(
            px, py, corridor[0], corridor[1], map_key=gs.map_key, state=state
        ):
            return corridor
    if climb in walked and (px, py) == (ROUTE_29_GATE_APPROACH_X, climb[1]):
        if (25, 10) in walked:
            return (25, 10)
        if find_path(
            px, py, ledge[0], ledge[1], map_key=gs.map_key, state=state
        ):
            return ledge
    if (
        climb in walked
        and ledge not in walked
        and py == climb[1] - 1
        and ROUTE_29_GATE_APPROACH_X <= px < ledge[0]
    ):
        if find_path(
            px, py, ledge[0], ledge[1], map_key=gs.map_key, state=state
        ):
            return ledge
    if py == ledge[1] and ROUTE_29_GATE_APPROACH_X <= px < ledge[0]:
        # At y=10 on the approach column (live route29_gate_approach): south
        # corridor is west progress; east to ledge (27,10) re-enters climb thrash.
        corridor = ROUTE_29_SOUTH_CORRIDOR
        if find_path(
            px, py, corridor[0], corridor[1], map_key=gs.map_key, state=state
        ):
            return corridor
        if find_path(
            px, py, ledge[0], ledge[1], map_key=gs.map_key, state=state
        ):
            return ledge
    if climb in walked and ledge in walked and (px, py) == (25, 10):
        if find_path(
            px, py, west[0], west[1], map_key=gs.map_key, state=state
        ):
            return west
    if (
        climb in walked
        and not skip_ledge_reclimb
        and py == climb[1]
        and reentry[0] <= px < ROUTE_29_GATE_APPROACH_X
    ):
        if find_path(
            px, py, ledge[0], ledge[1], map_key=gs.map_key, state=state
        ):
            return ledge
    on_gate_approach_column = (
        (px == ROUTE_29_GATE_APPROACH_X and py <= climb[1])
        or (py == reentry[1] and px > reentry[0])
    )
    if py == 11 and px >= ledge[0] - 1:
        if find_path(
            px, py, west[0], west[1], map_key=gs.map_key, state=state
        ):
            return west
        approach = ROUTE_29_WEST_GATE_APPROACH
        if find_path(
            px, py, approach[0], approach[1], map_key=gs.map_key, state=state
        ):
            return approach
    if not on_gate_approach_column and py == 11 and reentry[0] <= px < ledge[0]:
        if find_path(
            px, py, ledge[0], ledge[1], map_key=gs.map_key, state=state
        ):
            return ledge
    on_ledge_climb = (py, px) == (reentry[1], reentry[0]) or (
        reentry[1] - 2 <= py < reentry[1]
        and reentry[0] <= px < ROUTE_29_GATE_APPROACH_X
    )
    if not on_gate_approach_column and on_ledge_climb and not skip_ledge_reclimb:
        if find_path(
            px, py, climb[0], climb[1], map_key=gs.map_key, state=state
        ):
            return climb
    if west_complete and px >= 14 and py >= reentry[1]:
        west_row = _route_29_west_corridor_waypoint(
            px, py, map_key=gs.map_key, state=state
        )
        if west_row is not None:
            gate_path = find_path(
                px, py, gate[0], gate[1], map_key=gs.map_key, state=state
            )
            if gate_path and not _route_29_gate_path_drifts_east(gate_path):
                return west_row
    if west_complete and py >= reentry[1] and px <= ROUTE_29_GATE_APPROACH_X:
        if px <= ROUTE_29_WEST_GATE_APPROACH[0] + 2:
            gate_path = find_path(
                px, py, gate[0], gate[1], map_key=gs.map_key, state=state
            )
            if gate_path and not _route_29_gate_path_drifts_east(gate_path):
                return target
    if not west_complete and py >= 14 and px < reentry[0]:
        if find_path(
            px, py, reentry[0], reentry[1], map_key=gs.map_key, state=state
        ):
            return reentry
        return target
    if (
        not west_complete
        and py > reentry[1]
        and reentry[0] <= px <= ROUTE_29_GATE_APPROACH_X
    ):
        if find_path(
            px, py, reentry[0], reentry[1], map_key=gs.map_key, state=state
        ):
            return reentry
    if py < 10 or px <= ROUTE_29_SOUTH_CORRIDOR[0]:
        return target
    if ledge in walked and west_complete and py >= reentry[1] and px >= reentry[0]:
        return target
    corridor = ROUTE_29_SOUTH_CORRIDOR
    if not find_path(
        px, py, corridor[0], corridor[1], map_key=gs.map_key, state=state
    ):
        return target
    if on_gate_approach_column and py <= climb[1]:
        # Prefer south corridor west of the climb thrash when already at/west of
        # the approach column — ledge connector (27,10) is *east* and re-opens
        # the y=14 climb loop (live gate_approach thrash at 22,13↔22,14).
        if find_path(
            px, py, corridor[0], corridor[1], map_key=gs.map_key, state=state
        ):
            return corridor
        if find_path(
            px, py, ledge[0], ledge[1], map_key=gs.map_key, state=state
        ):
            return ledge
        if find_path(
            px, py, climb[0], climb[1], map_key=gs.map_key, state=state
        ):
            return climb
    if on_gate_approach_column:
        return corridor
    if py == 11 and px > west[0]:
        approach = ROUTE_29_WEST_GATE_APPROACH
        if find_path(
            px, py, approach[0], approach[1], map_key=gs.map_key, state=state
        ):
            return approach
    gate_path = find_path(
        px, py, gate[0], gate[1], map_key=gs.map_key, state=state
    )
    if gate_path and not _route_29_gate_path_drifts_east(gate_path):
        return target
    return corridor


def _lab_entrance_approach(
    gs: GameState,
    door: tuple[int, int],
    state: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """South approach tile when west of the discovered lab door."""
    from src.graph.pathfinding import find_path

    px, py = gs.player.x, gs.player.y
    approach = (door[0], door[1] + 1)
    if (px, py) in (door, approach):
        return door
    if py == approach[1] and px < approach[0]:
        return approach
    if find_path(
        px, py, approach[0], approach[1], map_key=gs.map_key, state=state
    ):
        return approach
    return door


def _starter_quest_landmark_id(gs: GameState, state: dict[str, Any]) -> str | None:
    from src.graph.phases import starter_quest
    from src.graph.quest_geography import retired_geography_landmark_id

    if not state.get("house_exit_complete"):
        return None
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_quest.has_starter(gs)
        and not starter_quest._has_egg(gs)
    ):
        return ELMS_LAB_EXIT_ID
    interior_id = starter_quest.interior_landmark_id(gs, state)
    if interior_id is not None:
        return interior_id
    if gs.map_key == MAP_KEY_NEW_BARK_TOWN and not starter_quest.has_starter(gs):
        return ELMS_LAB_ENTRANCE_ID
    if gs.map_key == MAP_KEY_MR_POKEMONS_HOUSE and not starter_quest._has_egg(gs):
        return MR_POKEMONS_HOUSE_ENTRANCE_ID
    if (
        gs.map_key == MAP_KEY_ELMS_LAB
        and starter_quest._has_egg(gs)
        and not starter_quest._egg_delivered(gs)
    ):
        # Prefer desk approach (seeded or known) — interior may be stamped at
        # door (4,11) on entry and would keep the agent on the warp tile.
        from src.memory.landmarks import ELMS_LAB_DESK_APPROACH_ID

        landmarks = list(state.get("known_landmarks", []))
        desk = find_landmark(landmarks, landmark_id=ELMS_LAB_DESK_APPROACH_ID)
        if desk is not None:
            return ELMS_LAB_DESK_APPROACH_ID
        interior = find_landmark(landmarks, landmark_id=ELMS_LAB_INTERIOR_ID)
        if interior is not None:
            # Only use interior if it is not the south door (egg-return thrash).
            ix, iy = interior.get("x"), interior.get("y")
            if not (iy == 11 and ix in (4, 5)):
                return ELMS_LAB_INTERIOR_ID
        return ELMS_LAB_DESK_APPROACH_ID
    return retired_geography_landmark_id(gs, state)


def resolve_landmark_navigation_target(
    gs: GameState,
    state: dict[str, Any],
) -> tuple[int, int] | None:
    """Resolve target from known_landmarks for the current map and quest stage."""
    from src.memory.landmarks import ELMS_LAB_DESK_APPROACH_ID

    landmarks = list(state.get("known_landmarks", []))
    landmark_id = _starter_quest_landmark_id(gs, state)
    if landmark_id:
        coords = _landmark_target_on_map(landmarks, landmark_id, gs.map_key)
        if coords is None and landmark_id == ELMS_LAB_DESK_APPROACH_ID:
            # Seeded anchor when desk landmark not yet in known_landmarks.
            coords = MAP_LANDMARK_ANCHORS.get(MAP_KEY_ELMS_LAB, {}).get(
                "desk_approach", (4, 3)
            )
        if coords is not None:
            if landmark_id == ELMS_LAB_ENTRANCE_ID:
                return _lab_entrance_approach(gs, coords, state)
            # West-corridor handoffs only for westbound R29 targets. Applying them
            # to route_29_east_exit hijacked egg-return into (10,8)/(4,10) west
            # thrash (live bed_egg_to_gym5: target [10,8] while subgoal was
            # "Give Mystery Egg to Elm").
            if landmark_id == ROUTE_29_EAST_EXIT_ID:
                # Live BFS (bed_egg bedroom_egg_r29): east is via south y14–16
                # corridor, not (17,5)/(17,6) which soft-locks. Pull south first.
                px, py = gs.player.x, gs.player.y
                if px < 45 and py < 14:
                    south_wp = (min(max(px, 14), 32), 14)
                    if find_path(
                        px, py, south_wp[0], south_wp[1],
                        map_key=gs.map_key, state=state,
                    ):
                        return south_wp
                return coords
            if landmark_id == ROUTE_29_WEST_EXIT_ID or (
                gs.map_key == MAP_KEY_ROUTE_29 and coords[0] < gs.player.x
            ):
                return _route_29_gate_south_corridor_waypoint(gs, coords, state)
            # Other same-map landmarks on R29: west-corridor handoffs only when
            # the landmark itself is west of the player.
            if gs.map_key == MAP_KEY_ROUTE_29 and coords[0] < gs.player.x:
                return _route_29_gate_south_corridor_waypoint(gs, coords, state)
            return coords

    return None


def resolve_navigation_target(
    gs: GameState,
    state: dict[str, Any],
    *,
    map_key: str | None = None,
) -> tuple[int, int]:
    """Landmark-first nav target; exploration frontier as fallback."""
    from src.graph.phases import house_exit

    map_key = map_key or gs.map_key
    house_target = house_exit.navigation_target(gs, map_key=map_key, state=state)
    if house_target is not None:
        return house_target

    landmark_target = resolve_landmark_navigation_target(gs, state)
    if landmark_target is not None:
        # Route 30 post-rival: east pocket thrash (x≥8, y≈6–40) — A* detours
        # south instead of west corridor to R31. Commit west strip first.
        if (
            state.get("starter_quest_complete")
            and gs.map_key == "26:1"
            and landmark_target[1] < gs.player.y
            and gs.player.x >= 8
            and 5 <= gs.player.y <= 45
        ):
            # East pocket (x≥8, y≤20) cannot go west on same row — drop to y=20
            # mid-join then west strip (live grid barrier at x6–7 north of ~y15).
            west_y = 20 if gs.player.y < 20 else min(gs.player.y, 30)
            west_strip = (5, west_y)
            if find_path(
                gs.player.x,
                gs.player.y,
                west_strip[0],
                west_strip[1],
                map_key="26:1",
                max_steps=80,
                state=state,
            ):
                return west_strip
        # Route 29 westbound: do not force a y=14 south-corridor interim from the
        # mid/north strip. Live Silver path from (36,10)/(59,8) goes via the y4
        # north bridge and y7 (grid closes y6 x9-16 false-opens). South detours
        # are already chosen by A* when the player is south of a one-way ledge.
        return landmark_target

    if state.get("starter_quest_complete"):
        from src.graph.phases import early_progression as ep

        if ep.in_early_progression(gs, state):
            return exploration_target(gs, state)

    if state.get("house_exit_complete"):
        return exploration_target(gs, state)

    return (gs.player.x + 1, gs.player.y)
