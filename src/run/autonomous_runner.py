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

logger = logging.getLogger(__name__)


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
    ):
        self.rom_path = Path(rom_path)
        self.max_steps = max_steps
        self.checkpoint_db = Path(checkpoint_db)
        self.save_dir = Path(save_dir)
        self.langsmith = langsmith
        self.thread_id = thread_id
        self.stuck_threshold = stuck_threshold
        self.memory = LongTermMemory()

        if langsmith:
            os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
            os.environ.setdefault("LANGSMITH_PROJECT", "pokemon-gold-agent")

    def _resolve_thread_id(self, resume: str | None) -> str:
        if resume == "latest":
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

        with PyBoyWrapper(self.rom_path, save_dir=self.save_dir) as emu:
            bind_emulator(emu)
            graph = compile_graph(emu, checkpoint_path=self.checkpoint_db)
            config = {"configurable": {"thread_id": thread_id}}

            if resume:
                try:
                    snapshot = graph.get_state(config)
                    state = snapshot.values if snapshot.values else create_initial_state(emu)
                    logger.info("Resumed from checkpoint thread_id=%s", thread_id)
                except Exception:
                    state = create_initial_state(emu)
            else:
                state = create_initial_state(emu)

            start_steps = state.get("metrics", {}).get("steps", 0)
            target_steps = start_steps + self.max_steps
            milestones: list[str] = list(state.get("milestones", []))

            while state.get("metrics", {}).get("steps", 0) < target_steps:
                current = state.get("metrics", {}).get("steps", 0)
                state["run_max_steps"] = current + 1
                state = graph.invoke(state, config=config)
                steps = state.get("metrics", {}).get("steps", 0)

                for m in state.get("milestones", []):
                    if m not in milestones:
                        milestones.append(m)
                        logger.info("MILESTONE: %s", m)
                        self.memory.add_fact(f"milestone:{m}")

                if state.get("stuck_count", 0) >= self.stuck_threshold:
                    logger.warning("Stuck count=%d, saving state", state["stuck_count"])
                    emu.save_state(f"stuck_{steps}")
                    state["should_replan"] = True
                    state["stuck_count"] = 0

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