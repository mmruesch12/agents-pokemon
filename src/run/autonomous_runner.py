"""Autonomous runner with checkpoints, stuck handling, and resume."""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.eval.evaluators import evaluate_run
from src.graph.graph import compile_graph, create_initial_state
from src.graph.phases import house_exit
from src.graph.state import AgentState
from src.state.models import GameState
from src.memory.landmarks import memory_data_dir
from src.memory.long_term_memory import LongTermMemory
from src.run._langsmith import build_invoke_config, configure_tracing

logger = logging.getLogger(__name__)


def _specialist_label(state: AgentState) -> str:
    """Infer which specialist produced last_action (not stored explicitly post-invoke)."""
    last_action = state.get("last_action", "")
    if last_action.startswith("bootstrap_") or state.get("phase") == "bootstrap":
        return "bootstrap"
    if last_action.startswith("navigate_"):
        return "navigator"
    if last_action.startswith("battle_"):
        return "battler"
    if state.get("phase") == "plan" or state.get("should_replan"):
        return "planner"
    return "supervisor"


def _subgoal_label(state: AgentState) -> str:
    if state.get("phase") == "bootstrap" or state.get("last_action", "").startswith("bootstrap_"):
        return "intro sequence"
    return state.get("active_subgoal", "") or "explore"


def format_intent_card(state: AgentState) -> str:
    """One-line HUD card from AgentState fields (post graph.invoke)."""
    steps = state.get("metrics", {}).get("steps", 0)
    specialist = _specialist_label(state)
    last_action = state.get("last_action", "") or "none"
    subgoal = _subgoal_label(state)
    critic = state.get("critic_verdict", "proceed")
    stuck = state.get("stuck_count", 0)
    facts = state.get("long_term_facts", [])
    replan = state.get("should_replan", False)

    gs = GameState.model_validate(state.get("game_state", {}))
    map_ctx = house_exit.format_map_context(gs)

    return (
        f"[step {steps}] {specialist} → {last_action} | "
        f"subgoal: {subgoal} | map: {map_ctx} | critic: {critic} | "
        f"stuck: {stuck} | facts: {len(facts)} | replan: {replan}"
    )


def log_intent_card(state: AgentState) -> None:
    """Emit the post-invoke intent card at INFO (called from the runner loop)."""
    logger.info("%s", format_intent_card(state))


class AutonomousRunner:
    """Long-running autonomous agent harness."""

    def __init__(
        self,
        rom_path: str | Path,
        *,
        max_steps: int = 5000,
        checkpoint_db: str | Path = "data/checkpoints.sqlite",
        save_dir: str | Path = "saves",
        langsmith: bool = False,
        thread_id: str = "default",
        stuck_threshold: int = 10,
        headed: bool = False,
        window: str | None = None,
        start_bedroom: bool = False,
        bedroom_state_name: str | None = None,
        start_lab: bool = False,
        emulator_state: str | None = None,
        lab_state_name: str | None = None,
    ):
        self.rom_path = Path(rom_path)
        self.max_steps = max_steps
        self.checkpoint_db = Path(checkpoint_db)
        self.save_dir = Path(save_dir)
        self.langsmith = langsmith
        self.thread_id = thread_id
        self.stuck_threshold = stuck_threshold
        self.headed = headed
        self.window = window
        self.start_bedroom = start_bedroom
        self.bedroom_state_name = bedroom_state_name
        self.start_lab = start_lab
        self.emulator_state = emulator_state
        self.lab_state_name = lab_state_name
        self.memory = LongTermMemory(data_dir=memory_data_dir())

        configure_tracing(langsmith=langsmith, headed=headed)

    def _validate_fast_start(self, resume: str | None) -> None:
        fast_flags = (
            self.start_bedroom,
            self.start_lab,
            bool(self.emulator_state),
        )
        if sum(fast_flags) > 1:
            raise ValueError(
                "Use only one of --start-bedroom, --start-lab, or --emulator-state"
            )
        if resume and any(fast_flags):
            raise ValueError(
                "Fast-start flags (--start-bedroom, --start-lab, --emulator-state) "
                "cannot be used with --resume"
            )

    def _bootstrap_if_needed(self, emu: Any, state: AgentState) -> AgentState:
        from src.emulator.bootstrap import (
            apply_bootstrap_metadata,
            needs_bootstrap,
            run_bootstrap,
        )
        from src.graph.state import update_game_state
        from src.state.models import GameState

        gs = GameState.model_validate(state.get("game_state", {}))
        if not needs_bootstrap(gs, state):
            return state

        logger.info("Cold boot detected — running intro bootstrap")
        from src.emulator.bootstrap import INDOOR_BOOTSTRAP_ACTIONS

        result = run_bootstrap(emu, rom_path=self.rom_path)
        gs = apply_bootstrap_metadata(emu.get_game_state(), result)
        state = update_game_state(state, gs)
        state["bootstrap_complete"] = result.movement_ready
        state["phase"] = "explore" if result.movement_ready else "bootstrap"
        if result.movement_ready:
            state["bootstrap_action_index"] = INDOOR_BOOTSTRAP_ACTIONS
        if result.map_loaded:
            logger.info(
                "Bootstrap map loaded in %d actions (%d frames); graph bootstrap will continue",
                result.actions_taken,
                result.frames_elapsed,
            )
        else:
            logger.warning(
                "Bootstrap incomplete after %d actions; graph bootstrap node will continue",
                result.actions_taken,
            )
        return state

    def _seed_state_from_loaded_emulator(self, emu: Any, save_name: str) -> AgentState:
        """Build agent state from emulator RAM after loading a .state file."""
        from src.emulator.bootstrap import (
            INDOOR_BOOTSTRAP_ACTIONS,
            MIN_GRAPH_BOOTSTRAP_ACTIONS,
            in_loaded_map,
            is_bootstrap_done,
            read_loaded_map,
        )
        from src.graph.state import update_game_state

        gs = emu.get_game_state()
        state = create_initial_state(emu)
        state = update_game_state(state, gs)
        if gs.party_count > 0:
            state["bootstrap_complete"] = True
            state["phase"] = "explore"
            state["bootstrap_action_index"] = MIN_GRAPH_BOOTSTRAP_ACTIONS
        elif in_loaded_map(emu):
            state["bootstrap_action_index"] = INDOOR_BOOTSTRAP_ACTIONS
            bootstrap_done = is_bootstrap_done(emu, gs, state)
            state["bootstrap_complete"] = bootstrap_done
            state["phase"] = "explore" if bootstrap_done else "bootstrap"
        else:
            state["bootstrap_complete"] = False
            state["phase"] = "bootstrap"

        state["should_replan"] = False
        logger.info(
            "Seeded agent from emulator save %s (map=%s, bootstrap_complete=%s)",
            save_name,
            read_loaded_map(emu),
            state["bootstrap_complete"],
        )
        return state

    def _hard_reload_candidates(self, *, progress_written: bool = False) -> list[str]:
        """Save basenames to try on hard soft-lock recovery (first existing wins).

        Prefer free progress tiles written *this run* (when ``progress_written``),
        then *this run's* original fast-start snapshot. Never hardcode foreign
        session basenames (``bed_chain_*``, ``bedroom_egg_*``) — those teleport
        mid-quest and invalidate continuous bedroom_start proof. Also skip
        leftover ``progress_checkpoint*`` files from prior processes until this
        run has stamped free progress itself.
        """
        candidates: list[str] = []
        if progress_written:
            candidates.extend(
                [
                    "progress_checkpoint_safe",
                    "progress_checkpoint_prev",
                    "progress_checkpoint",
                ]
            )
        if self.emulator_state:
            candidates.append(self.emulator_state)
        if self.start_bedroom:
            candidates.append("bedroom_start")
        if self.start_lab:
            candidates.append("lab_desk_start")
        return candidates

    def _load_latest_emulator_state(self, emu: Any) -> str | None:
        """Load the newest emulator .state file (headed watch resume)."""
        states = sorted(
            self.save_dir.glob("*.state"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not states:
            return None
        name = states[0].stem
        try:
            emu.load_state(name)
            logger.info("Loaded emulator state from latest save: %s", name)
            return name
        except Exception as exc:
            logger.warning("Could not load latest emulator state %s: %s", name, exc)
            return None

    def _reset_checkpoint_thread(
        self, checkpoint_db: Path, thread_id: str
    ) -> None:
        """Drop stale LangGraph rows so fast-start snapshots replace agent state."""
        if not checkpoint_db.is_file():
            return
        try:
            conn = sqlite3.connect(str(checkpoint_db))
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            logger.warning("Could not reset checkpoint thread %s: %s", thread_id, exc)

    def _resolve_thread_id(self, resume: str | None) -> str:
        if resume == "latest":
            if self.headed:
                return self.thread_id
            if self.checkpoint_db.exists():
                conn = sqlite3.connect(str(self.checkpoint_db))
                row = conn.execute(
                    "SELECT thread_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1"
                ).fetchone()
                conn.close()
                if row:
                    return row[0]
            return self.thread_id
        return resume or self.thread_id

    def run(self, *, resume: str | None = None) -> dict[str, Any]:
        from src.emulator.pyboy_wrapper import PyBoyWrapper
        from src.tools.pokemon_tools import bind_emulator

        self._validate_fast_start(resume)

        thread_id = self._resolve_thread_id(resume)
        if self.start_bedroom and self.thread_id == "default":
            thread_id = "bedroom"
        elif self.start_lab and self.thread_id == "default":
            thread_id = "lab"
        elif self.emulator_state and self.thread_id == "default":
            thread_id = f"emu-{self.emulator_state}"
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

        if not self.rom_path.exists():
            raise FileNotFoundError(
                f"ROM not found: {self.rom_path}. Place a legal ROM at roms/pokemon_gold.gb"
            )

        effective_window = self.window if self.window is not None else ("SDL2" if self.headed else "null")
        configure_tracing(langsmith=self.langsmith, headed=self.headed)
        from src.emulator.battery_save import isolated_battery_files

        with isolated_battery_files(self.rom_path):
            with PyBoyWrapper(
                self.rom_path, window=effective_window, save_dir=self.save_dir
            ) as emu:
                bind_emulator(emu)

                if self.headed:
                    try:
                        from langgraph.checkpoint.memory import MemorySaver

                        checkpointer = MemorySaver()
                    except ImportError:
                        checkpointer = None
                    graph = compile_graph(
                        emu, checkpoint_path=None, checkpointer=checkpointer
                    )
                else:
                    graph = compile_graph(emu, checkpoint_path=self.checkpoint_db)
                checkpoint_config = {"configurable": {"thread_id": thread_id}}
                if resume:
                    loaded_name = None
                    if self.headed:
                        loaded_name = self._load_latest_emulator_state(emu)
                    state = None
                    try:
                        snapshot = graph.get_state(checkpoint_config)
                        if snapshot.values:
                            state = snapshot.values
                            logger.info("Resumed agent checkpoint thread_id=%s", thread_id)
                    except Exception:
                        state = None
                    if state is None:
                        if loaded_name:
                            state = self._seed_state_from_loaded_emulator(emu, loaded_name)
                        else:
                            state = create_initial_state(emu)
                            logger.info("Fresh agent state thread_id=%s", thread_id)
                elif self.start_bedroom:
                    from src.emulator.bootstrap import prepare_bedroom_start

                    state = create_initial_state(emu)
                    state = prepare_bedroom_start(
                        emu,
                        state,
                        rom_path=self.rom_path,
                        save_dir=self.save_dir,
                        bedroom_state_name=self.bedroom_state_name,
                    )
                    logger.info(
                        "Bedroom start ready (map=%s, bootstrap_complete=%s)",
                        state.get("game_state", {}).get("player", {}).get("map_name"),
                        state.get("bootstrap_complete"),
                    )
                elif self.start_lab:
                    from src.emulator.bootstrap import prepare_lab_start

                    state = create_initial_state(emu)
                    state = prepare_lab_start(
                        emu,
                        state,
                        save_dir=self.save_dir,
                        lab_state_name=self.lab_state_name,
                    )
                    logger.info(
                        "Lab start ready (map=%s, subgoal=%s)",
                        state.get("game_state", {}).get("player", {}).get("map_name"),
                        state.get("active_subgoal"),
                    )
                elif self.emulator_state:
                    from src.emulator.bootstrap import prepare_emulator_state

                    state = create_initial_state(emu)
                    state = prepare_emulator_state(
                        emu,
                        state,
                        self.emulator_state,
                        save_dir=self.save_dir,
                    )
                    logger.info(
                        "Emulator state %s ready (map=%s, subgoal=%s)",
                        self.emulator_state,
                        state.get("game_state", {}).get("player", {}).get("map_name"),
                        state.get("active_subgoal"),
                    )
                else:
                    state = create_initial_state(emu)
                    state = self._bootstrap_if_needed(emu, state)

                state = self.memory.hydrate_state(state)

                fast_start = not resume and (
                    self.start_lab or self.start_bedroom or bool(self.emulator_state)
                )
                if fast_start:
                    state.setdefault("metrics", {})["steps"] = 0
                    self._reset_checkpoint_thread(self.checkpoint_db, thread_id)
                    try:
                        graph.update_state(checkpoint_config, state)
                        logger.info(
                            "Seeded checkpointer thread_id=%s from fast-start snapshot",
                            thread_id,
                        )
                    except Exception as exc:
                        logger.warning("Could not seed checkpointer: %s", exc)

                start_steps = state.get("metrics", {}).get("steps", 0)
                target_steps = start_steps + self.max_steps
                milestones: list[str] = list(state.get("milestones", []))
                last_progress_pos: str | None = None
                softlock_reloads = 0
                # Runner-local: only trust progress_checkpoint* files after *this*
                # run stamps free progress (ignore leftover files from prior runs).
                progress_written = False
                progress_safe_map: str | None = None
                progress_safe_pos: str | None = None

                while state.get("metrics", {}).get("steps", 0) < target_steps:
                    current = state.get("metrics", {}).get("steps", 0)
                    state["run_max_steps"] = current + 1
                    invoke_config = build_invoke_config(
                        state,
                        thread_id=thread_id,
                        headed=self.headed,
                    )
                    state = graph.invoke(state, config=invoke_config)
                    steps = state.get("metrics", {}).get("steps", 0)
                    log_intent_card(state)

                    # Emit compact snapshot for dashboard UI (data/watch/current.{json,png})
                    try:
                        from src.run.dashboard_server import emit_snapshot

                        png_bytes: bytes | None = None
                        try:
                            png_bytes = emu.screenshot()
                        except Exception:
                            png_bytes = None
                        emit_snapshot(state, png_bytes)
                    except Exception:
                        # Dashboard emission is best-effort; never break the run loop
                        pass

                    for m in state.get("milestones", []):
                        if m not in milestones:
                            milestones.append(m)
                            logger.info("MILESTONE: %s", m)
                            self.memory.add_fact(f"milestone:{m}")

                    if state.get("known_landmarks"):
                        self.memory.sync_landmarks_from_state(state)

                    # Progress checkpoint: freely-moving tile with real displacement
                    # so hard soft-lock reload does not land on the same stuck tile
                    # (live R30 (14,23) overwrote checkpoint then reloaded itself).
                    # Never checkpoint while outdoor textbox/script is open — that
                    # saved (1,7)/(12,14) soft-locks as "progress" (bed_chain_gym).
                    gs_now = GameState.model_validate(state.get("game_state", {}))
                    pos_now = gs_now.position_key
                    meta_now = gs_now.raw_metadata or {}
                    script_open = bool(
                        gs_now.in_text_box
                        or meta_now.get("in_script")
                        or meta_now.get("script_active")
                        or int(meta_now.get("script_mode") or 0) != 0
                    )
                    frozen_now = int(state.get("outdoor_script_frozen_count", 0))
                    if (
                        int(state.get("stuck_count", 0)) == 0
                        and pos_now
                        and not script_open
                        and frozen_now == 0
                    ):
                        prev = last_progress_pos
                        far_enough = True
                        if prev and prev.count(":") == 3 and pos_now.count(":") == 3:
                            try:
                                pm, px, py = prev.rsplit(":", 2)
                                nm, nx, ny = pos_now.rsplit(":", 2)
                                far_enough = pm != nm or abs(int(px) - int(nx)) + abs(
                                    int(py) - int(ny)
                                ) >= 3
                            except ValueError:
                                far_enough = pos_now != prev
                        else:
                            far_enough = pos_now != prev
                        if far_enough:
                            try:
                                import shutil

                                # Keep previous good tile for double-buffer reload.
                                if (self.save_dir / "progress_checkpoint.state").is_file():
                                    shutil.copy(
                                        self.save_dir / "progress_checkpoint.state",
                                        self.save_dir / "progress_checkpoint_prev.state",
                                    )
                                emu.save_state("progress_checkpoint")
                                # Safe snapshot for hard reload: create once, then
                                # refresh on map advance OR significant free progress
                                # on the same map (live gym29: whole R30 is one map —
                                # map-only refresh left safe at west seed and a soft-
                                # lock reload wiped ~50 northbound steps).
                                safe = self.save_dir / "progress_checkpoint_safe.state"
                                cur_map = gs_now.map_key
                                map_advanced = (
                                    progress_safe_map is not None
                                    and progress_safe_map != cur_map
                                )
                                # Same-map: require Manhattan ≥8 from last safe tile so
                                # we keep free mid-route recovery without thrash-overwrite.
                                significant_same = False
                                if (
                                    progress_safe_map == cur_map
                                    and progress_safe_pos
                                    and progress_safe_pos.count(":") == 3
                                    and pos_now.count(":") == 3
                                ):
                                    try:
                                        _sm, sx, sy = progress_safe_pos.rsplit(":", 2)
                                        _nm, nx, ny = pos_now.rsplit(":", 2)
                                        significant_same = (
                                            abs(int(sx) - int(nx))
                                            + abs(int(sy) - int(ny))
                                            >= 8
                                        )
                                    except ValueError:
                                        significant_same = False
                                # First free progress of the run: always stamp safe to
                                # the current free tile (pre-copied seed files must not
                                # block updates — live gym29 left safe at (5,30) forever).
                                first_safe = progress_safe_map is None
                                if (
                                    (not safe.is_file())
                                    or map_advanced
                                    or significant_same
                                    or first_safe
                                ):
                                    shutil.copy(
                                        self.save_dir / "progress_checkpoint.state",
                                        safe,
                                    )
                                    progress_safe_map = cur_map
                                    progress_safe_pos = pos_now
                                    logger.info(
                                        "Updated progress_checkpoint_safe on map %s @ %s",
                                        cur_map,
                                        pos_now,
                                    )
                                last_progress_pos = pos_now
                                progress_written = True
                            except Exception as exc:
                                logger.debug("progress checkpoint save failed: %s", exc)

                    stuck_now = int(state.get("stuck_count", 0))
                    frozen_now = int(state.get("outdoor_script_frozen_count", 0))
                    no_prog_now = int(state.get("interact_no_progress_count", 0))
                    # Outdoor SCRIPT_READ soft-lock: pure A never clears — also
                    # trigger hard reload from long freeze alone (stuck may lag).
                    # Thresholds sit *above* supervisor outdoor breakout (frozen≥5 /
                    # no_prog≥6) so path0 can leave the tile before we reload.
                    outdoor_softlock = (
                        frozen_now >= 14
                        or no_prog_now >= 14
                        or (frozen_now >= 8 and no_prog_now >= 10)
                        or (stuck_now >= 8 and frozen_now >= 6)
                    )
                    if stuck_now >= self.stuck_threshold or outdoor_softlock:
                        if stuck_now >= self.stuck_threshold:
                            logger.warning(
                                "Stuck count=%d (failed moves), saving state",
                                stuck_now,
                            )
                            emu.save_state(f"stuck_{steps}")
                            state["should_replan"] = True
                            gs = GameState.model_validate(state.get("game_state", {}))
                            self.memory.capture_stuck_episode(state, gs)
                        # Hard soft-lock: stuck high on one tile — reload last good
                        # progress (live R30 (13,24)/(12,14) frozen script_pos;
                        # pure A/B never clear). Threshold lowered from +10/18 so
                        # thrash-elevated stuck triggers reload before step budget dies.
                        frozen = frozen_now
                        # Always allow hard reload at stuck_threshold once stuck
                        # saves fire — outdoor soft-locks often have frozen=0 while
                        # navigate_a thrash keeps stuck elevated (live R30 (4,4)).
                        hard_need = (
                            max(self.stuck_threshold - 2, 6)
                            if frozen >= 4
                            else max(self.stuck_threshold, 10)
                        )
                        # Multi-page Elm egg-return dialog at the lab desk needs
                        # dozens of A presses; hard-reload to door (4,11) aborts
                        # delivery (live bed_egg_to_gym17). Skip indoor lab reloads
                        # while egg is still held.
                        gs_sl = GameState.model_validate(state.get("game_state", {}))
                        meta_sl = gs_sl.raw_metadata or {}
                        egg_lab_dialog = bool(
                            gs_sl.map_key in ("24:5", "24:4")
                            and meta_sl.get("has_mystery_egg")
                            and not meta_sl.get("egg_delivered")
                        )
                        if (
                            (
                                int(state.get("stuck_count", 0)) >= hard_need
                                or outdoor_softlock
                            )
                            and softlock_reloads < 24
                            and not egg_lab_dialog
                        ):
                            reload_name = None
                            candidates = self._hard_reload_candidates(
                                progress_written=progress_written
                            )
                            for candidate in candidates:
                                if (self.save_dir / f"{candidate}.state").is_file():
                                    reload_name = candidate
                                    break
                            if reload_name:
                                try:
                                    emu.load_state(reload_name)
                                    gs_reload = emu.get_game_state()
                                    # Prefer prev if current softlock pos matches checkpoint.
                                    if (
                                        reload_name == "progress_checkpoint"
                                        and gs_reload.position_key == pos_now
                                        and (
                                            self.save_dir / "progress_checkpoint_prev.state"
                                        ).is_file()
                                    ):
                                        emu.load_state("progress_checkpoint_prev")
                                        gs_reload = emu.get_game_state()
                                        reload_name = "progress_checkpoint_prev"
                                    # Skip checkpoint if it is itself soft-locked text.
                                    meta_r = gs_reload.raw_metadata or {}
                                    if gs_reload.in_text_box or meta_r.get("in_script"):
                                        alt = (
                                            "progress_checkpoint_prev"
                                            if reload_name == "progress_checkpoint"
                                            else None
                                        )
                                        if alt and (
                                            self.save_dir / f"{alt}.state"
                                        ).is_file():
                                            emu.load_state(alt)
                                            gs_reload = emu.get_game_state()
                                            reload_name = alt
                                            meta_r = gs_reload.raw_metadata or {}
                                        if gs_reload.in_text_box or meta_r.get(
                                            "in_script"
                                        ):
                                            logger.warning(
                                                "Hard soft-lock: checkpoint %s also "
                                                "in script/textbox — skip reload",
                                                reload_name,
                                            )
                                            raise RuntimeError(
                                                "softlock checkpoint unusable"
                                            )
                                    from src.graph.state import update_game_state
                                    from src.graph.pathfinding import record_session_blocked

                                    # Remember soft-lock tile before state rewrite.
                                    soft_pos = pos_now
                                    state = update_game_state(state, gs_reload)
                                    state["stuck_count"] = 0
                                    state["interact_no_progress_count"] = 0
                                    state["outdoor_script_frozen_count"] = 0
                                    state["recent_nav_positions"] = []
                                    state["stuck_replan_loops"] = 0
                                    state["interact_stall_escape_fails"] = 0
                                    state["interact_stall_escape"] = False
                                    state["pocket_stuck_count"] = 0
                                    state["pocket_nav_positions"] = []
                                    # Keep only the soft-lock tile blocked — wiping
                                    # everything then re-blocking that tile. Accumulating
                                    # dozens of session blocks after many reloads forced
                                    # worse paths into more soft-locks (live gym25).
                                    state["session_blocked"] = {}
                                    if soft_pos and soft_pos.count(":") == 3:
                                        try:
                                            sm, sx, sy = soft_pos.rsplit(":", 2)
                                            record_session_blocked(
                                                state, sm, int(sx), int(sy)
                                            )
                                        except ValueError:
                                            pass
                                    state["should_replan"] = True
                                    softlock_reloads += 1
                                    logger.warning(
                                        "Hard soft-lock recovery: reloaded %s (%s) reload#%d",
                                        reload_name,
                                        gs_reload.position_key,
                                        softlock_reloads,
                                    )
                                except Exception as exc:
                                    logger.warning(
                                        "Hard soft-lock reload failed: %s", exc
                                    )

                    if steps > 0 and steps % 100 == 0:
                        scores = evaluate_run(state)
                        logger.info(
                            "Step %d: progress=%.3f stuck=%.3f coherence=%.2f",
                            steps,
                            scores["progress_per_steps"],
                            scores["stuck_frequency"],
                            scores["coherence"],
                        )
                        self.memory.summarize_history(state.get("short_term_history", []))

                    if state.get("error"):
                        logger.error("Error: %s", state["error"])
                        break

                final_steps = state.get("metrics", {}).get("steps", 0)
                emu.save_state(f"final_{final_steps}")
                scores = evaluate_run(state)

                player = state.get("game_state", {}).get("player", {})
                return {
                    "steps": final_steps,
                    "milestones": milestones,
                    "thread_id": thread_id,
                    "scores": scores,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "final_map_key": f"{player.get('map_group')}:{player.get('map_id')}",
                    "final_map_name": player.get("map_name"),
                    "final_position": (player.get("x"), player.get("y")),
                }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Pokemon Gold/Silver agent runner")
    parser.add_argument("--rom", default=os.environ.get("ROM_PATH", "roms/pokemon_gold.gb"))
    parser.add_argument("--max-steps", type=int, default=int(os.environ.get("MAX_STEPS", "5000")))
    parser.add_argument("--resume", default=None, help="Resume from 'latest' or thread_id")
    parser.add_argument("--langsmith", action="store_true")
    parser.add_argument("--checkpoint-db", default=os.environ.get("CHECKPOINT_DB", "data/checkpoints.sqlite"))
    parser.add_argument("--save-dir", default=os.environ.get("SAVE_DIR", "saves"))
    parser.add_argument("--thread-id", default="default")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--headed", action="store_true", help="Enable visible SDL2 window so you can watch the agent play (default is headless)")
    parser.add_argument(
        "--start-bedroom",
        action="store_true",
        help="Skip title/bootstrap graph work; fast-forward to Player's House 2F (caches saves/bedroom_start.state)",
    )
    parser.add_argument(
        "--bedroom-state-name",
        default=None,
        help="Custom name for bedroom start save state (default via BEDROOM_START_STATE env)",
    )
    parser.add_argument(
        "--start-lab",
        action="store_true",
        help="Fast-start from saves/lab_desk_start.state at Elm's lab (see capture-lab-start)",
    )
    parser.add_argument(
        "--emulator-state",
        default=None,
        metavar="NAME",
        help="Load saves/NAME.state and seed agent flags for that map (not compatible with --resume)",
    )
    parser.add_argument(
        "--lab-state-name",
        default=None,
        help="Custom lab desk snapshot name for --start-lab (default via LAB_DESK_START_STATE env)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.max_steps == 0:
        parser.print_help()
        return 0

    try:
        runner = AutonomousRunner(
            rom_path=args.rom,
            max_steps=args.max_steps,
            checkpoint_db=args.checkpoint_db,
            save_dir=args.save_dir,
            langsmith=args.langsmith,
            thread_id=args.thread_id,
            headed=getattr(args, "headed", False),
            start_bedroom=getattr(args, "start_bedroom", False),
            bedroom_state_name=getattr(args, "bedroom_state_name", None),
            start_lab=getattr(args, "start_lab", False),
            emulator_state=getattr(args, "emulator_state", None),
            lab_state_name=getattr(args, "lab_state_name", None),
        )
        result = runner.run(resume=args.resume)
        print(f"Completed {result['steps']} steps")
        print(f"Milestones: {result['milestones']}")
        print(
            f"Final: {result.get('final_map_name')} "
            f"({result.get('final_map_key')}) at {result.get('final_position')}"
        )
        print(f"Scores: {result['scores']}")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())