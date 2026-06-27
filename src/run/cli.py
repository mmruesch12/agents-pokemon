"""CLI entry points: run, resume, eval, dashboard."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _setup_langsmith(enable: bool) -> None:
    if enable:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "pokemon-gold-agent")


def cmd_run(args: argparse.Namespace) -> int:
    from src.run.autonomous_runner import AutonomousRunner

    runner = AutonomousRunner(
        rom_path=args.rom,
        max_steps=args.steps,
        checkpoint_db=args.checkpoint_db,
        save_dir=args.save_dir,
        langsmith=args.langsmith,
        thread_id=args.thread_id,
    )
    result = runner.run(resume=args.resume)
    print(f"Run complete: {result['steps']} steps, milestones={result['milestones']}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from src.eval.datasets import get_dataset
    from src.eval.evaluators import evaluate_against_dataset, evaluate_run
    from src.graph.state import initial_agent_state

    dataset = get_dataset(args.dataset)
    print(f"Evaluating {len(dataset)} dataset entries...")
    for entry in dataset:
        state = initial_agent_state({"player": entry["input"], "battle": {"in_battle": entry["input"].get("in_battle", False)}})
        scores = evaluate_run(state)
        result = evaluate_against_dataset(state, entry)
        print(f"  {entry['id']}: coherence={scores['coherence']:.2f}, match={result['input_match']}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    print("Dashboard: use LangSmith at https://smith.langchain.com for traces")
    print(f"  Project: {os.environ.get('LANGSMITH_PROJECT', 'pokemon-gold-agent')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-gold-agent",
        description="Autonomous multi-agent Pokemon Gold/Silver player",
    )
    parser.add_argument("--rom", default=os.environ.get("ROM_PATH", "roms/pokemon_gold.gb"))
    parser.add_argument("--steps", type=int, default=int(os.environ.get("MAX_STEPS", "2000")))
    parser.add_argument("--resume", default=None, help="Resume from checkpoint thread_id or 'latest'")
    parser.add_argument("--langsmith", action="store_true", help="Enable LangSmith tracing")
    parser.add_argument("--checkpoint-db", default=os.environ.get("CHECKPOINT_DB", "data/checkpoints.sqlite"))
    parser.add_argument("--save-dir", default=os.environ.get("SAVE_DIR", "saves"))
    parser.add_argument("--thread-id", default="default")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--max-steps", type=int, dest="steps", help="Alias for --steps")

    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run agent for N steps")
    run_p.set_defaults(func=cmd_run)

    sub.add_parser("resume", help="Resume latest run").set_defaults(
        func=cmd_run, resume="latest"
    )

    eval_p = sub.add_parser("eval", help="Run evaluators on dataset")
    eval_p.add_argument("--dataset", default="early_game")
    eval_p.set_defaults(func=cmd_eval)

    sub.add_parser("dashboard", help="Dashboard info").set_defaults(func=cmd_dashboard)

    parser.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    _setup_langsmith(args.langsmith)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())