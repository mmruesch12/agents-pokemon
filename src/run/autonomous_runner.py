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
from src.graph.state import AgentState
from src.memory.long_term_memory import LongTermMemory
from src.run._langsmith import configure_tracing

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

    player = state.get("game_state", {}).get("player", {})
    map_name = player.get("map_name", "unknown")
    x = player.get("x", "?")
    y = player.get("y", "?")

    return (
        f"[step {steps}] {specialist} → {last_action} | "
        f"subgoal: {subgoal} | map: {map_name} ({x},{y}) | critic: {critic}"
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
        self.memory = LongTermMemory()

        configure_tracing(langsmith=langsmith, headed=headed)

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
        result = run_bootstrap(emu)
        gs = apply_bootstrap_metadata(emu.get_game_state(), result)
        state = update_game_state(state, gs)
        state["bootstrap_complete"] = False
        state["phase"] = "bootstrap"
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
        loaded_map = read_loaded_map(emu)
        state["loaded_map_key"] = loaded_map

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
            loaded_map,
            state["bootstrap_complete"],
        )
        return state

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

        thread_id = self._resolve_thread_id(resume)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

        if not self.rom_path.exists():
            raise FileNotFoundError(
                f"ROM not found: {self.rom_path}. Place a legal ROM at roms/pokemon_gold.gb"
            )

        effective_window = self.window if self.window is not None else ("SDL2" if self.headed else "null")
        configure_tracing(langsmith=self.langsmith, headed=self.headed)
        with PyBoyWrapper(self.rom_path, window=effective_window, save_dir=self.save_dir) as emu:
            bind_emulator(emu)

            if self.headed:
                try:
                    from langgraph.checkpoint.memory import MemorySaver

                    checkpointer = MemorySaver()
                except ImportError:
                    checkpointer = None
                graph = compile_graph(emu, checkpointer=checkpointer)
            else:
                graph = compile_graph(emu, checkpoint_path=self.checkpoint_db)
            config = {"configurable": {"thread_id": thread_id}}

            if resume:
                loaded_name = None
                if self.headed:
                    loaded_name = self._load_latest_emulator_state(emu)
                state = None
                try:
                    snapshot = graph.get_state(config)
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
            else:
                state = create_initial_state(emu)
                state = self._bootstrap_if_needed(emu, state)

            start_steps = state.get("metrics", {}).get("steps", 0)
            target_steps = start_steps + self.max_steps
            milestones: list[str] = list(state.get("milestones", []))

            while state.get("metrics", {}).get("steps", 0) < target_steps:
                current = state.get("metrics", {}).get("steps", 0)
                state["run_max_steps"] = current + 1
                state = graph.invoke(state, config=config)
                steps = state.get("metrics", {}).get("steps", 0)
                log_intent_card(state)

                for m in state.get("milestones", []):
                    if m not in milestones:
                        milestones.append(m)
                        logger.info("MILESTONE: %s", m)
                        self.memory.add_fact(f"milestone:{m}")

                if state.get("stuck_count", 0) >= self.stuck_threshold:
                    logger.warning(
                        "Stuck count=%d (failed moves), saving state", state["stuck_count"]
                    )
                    emu.save_state(f"stuck_{steps}")
                    state["should_replan"] = True

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

            return {
                "steps": final_steps,
                "milestones": milestones,
                "thread_id": thread_id,
                "scores": scores,
                "finished_at": datetime.now(timezone.utc).isoformat(),
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
        )
        result = runner.run(resume=args.resume)
        print(f"Completed {result['steps']} steps")
        print(f"Milestones: {result['milestones']}")
        print(f"Scores: {result['scores']}")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())