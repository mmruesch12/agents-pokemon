"""CLI entry points: run, resume, eval, dashboard."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from src.run._cli_flags import pop_store_true_flag
from src.run._langsmith import (
    configure_tracing,
    fetch_trace_details,
    format_trace_run,
    run_langsmith_cli,
    trace_project_name,
    trace_ui_url,
)

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _setup_langsmith(enable: bool, *, headed: bool = False) -> None:
    configure_tracing(langsmith=enable, headed=headed)


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume subcommand: default --resume to latest when omitted."""
    if args.resume is None:
        args.resume = "latest"
    return cmd_run(args)


def cmd_run(args: argparse.Namespace) -> int:
    from src.run.autonomous_runner import AutonomousRunner

    runner = AutonomousRunner(
        rom_path=args.rom,
        max_steps=args.steps,
        checkpoint_db=args.checkpoint_db,
        save_dir=args.save_dir,
        langsmith=args.langsmith,
        thread_id=args.thread_id,
        headed=getattr(args, "headed", False),
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
    project = trace_project_name()
    print(f"LangSmith project: {project}")
    print(f"  UI: {trace_ui_url()}")
    print("  Full traces (CLI):")
    print(f"    langsmith trace list --project {project} --full --show-hierarchy")
    print("    poke-agent traces --full")
    print("    poke-agent traces --trace-id <TRACE_ID>")
    return 0


def cmd_traces(args: argparse.Namespace) -> int:
    if args.full:
        args.use_cli = True
    project = trace_project_name()
    if not os.getenv("LANGSMITH_API_KEY", "").strip():
        print("LANGSMITH_API_KEY is not set. Add it to .env to fetch traces.", file=sys.stderr)
        return 1

    if args.trace_id:
        if args.use_cli:
            return run_langsmith_cli(
                ["trace", "get", args.trace_id, "--project", project, "--full"]
            )
        details = fetch_trace_details(args.trace_id, project=project)
        root = details["root"]
        print(f"Trace {args.trace_id} ({len(details['runs'])} runs)")
        for line in format_trace_run(root):
            print(line)
        child_ids = {r["id"] for r in details["runs"]} - {root["id"]}
        children = [r for r in details["runs"] if r["id"] in child_ids]
        children.sort(key=lambda r: r.get("start_time") or "")
        for child in children:
            for line in format_trace_run(child, indent=1):
                print(line)
        return 0

    limit = str(args.limit)
    if args.use_cli:
        return run_langsmith_cli(
            [
                "trace",
                "list",
                "--project",
                project,
                "--full",
                "--show-hierarchy",
                "-n",
                limit,
            ]
        )

    from langsmith import Client

    client = Client()
    runs = list(
        client.list_runs(
            project_name=project,
            is_root=True,
            limit=args.limit,
        )
    )
    if not runs:
        print(f"No traces in project '{project}'.")
        return 0

    print(f"Recent traces in '{project}' (use --trace-id for full IO):\n")
    for run in runs:
        meta = run.extra.get("metadata", {}) if run.extra else {}
        step = meta.get("step", "?")
        phase = meta.get("phase", meta.get("ls_integration", ""))
        action = meta.get("last_action", "")
        latency_ms = int((run.latency or 0) * 1000)
        print(
            f"  {run.id}  step={step}  phase={phase}  "
            f"action={action}  status={run.status}  {latency_ms}ms"
        )
    print("\nFull detail: poke-agent traces --trace-id <ID>")
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Common options so --headed / --steps etc. work in all these forms:
    #   cli --headed
    #   cli run --headed
    #   cli resume --headed
    #   cli --headed run ...
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--rom", default=os.environ.get("ROM_PATH", "roms/pokemon_gold.gb"))
    common.add_argument("--steps", type=int, default=int(os.environ.get("MAX_STEPS", "2000")))
    common.add_argument("--resume", default=None, help="Resume from checkpoint thread_id or 'latest'")
    common.add_argument("--langsmith", action="store_true", help="Enable LangSmith tracing")
    common.add_argument("--checkpoint-db", default=os.environ.get("CHECKPOINT_DB", "data/checkpoints.sqlite"))
    common.add_argument("--save-dir", default=os.environ.get("SAVE_DIR", "saves"))
    common.add_argument("--thread-id", default="default")
    common.add_argument("-v", "--verbose", action="store_true")
    common.add_argument("--max-steps", type=int, dest="steps", help="Alias for --steps")
    common.add_argument("--headed", action="store_true", help="Enable visible SDL2 window so you can watch the agent play (default is headless)")

    parser = argparse.ArgumentParser(
        prog="pokemon-gold-agent",
        description="Autonomous multi-agent Pokemon Gold/Silver player",
        parents=[common],
    )

    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", parents=[common], help="Run agent for N steps")
    run_p.set_defaults(func=cmd_run)

    resume_p = sub.add_parser("resume", parents=[common], help="Resume latest run")
    resume_p.set_defaults(func=cmd_resume)

    eval_p = sub.add_parser("eval", parents=[common], help="Run evaluators on dataset")
    eval_p.add_argument("--dataset", default="early_game")
    eval_p.set_defaults(func=cmd_eval)

    dashboard_p = sub.add_parser("dashboard", parents=[common], help="Dashboard info")
    dashboard_p.set_defaults(func=cmd_dashboard)

    traces_p = sub.add_parser("traces", parents=[common], help="List or inspect LangSmith traces")
    traces_p.add_argument("--trace-id", default=None, help="Show full IO for one trace")
    traces_p.add_argument("--limit", type=int, default=10, help="Max traces to list")
    traces_p.add_argument(
        "--full",
        action="store_true",
        help="When listing, prefer langsmith CLI hierarchy view (implies --use-cli)",
    )
    traces_p.add_argument(
        "--use-cli",
        action="store_true",
        help="Shell out to langsmith CLI (richer tree view)",
    )
    traces_p.set_defaults(func=cmd_traces)

    parser.set_defaults(func=cmd_run)
    return parser


def _parse_cli(argv: list[str] | None = None):
    """Thin wrapper for tests: returns the namespace after normalization + parse.

    This is the exact namespace that would be passed to cmd_run / runner.
    """
    parser = build_parser()
    raw = list(argv) if argv is not None else None
    headed_present, cleaned = pop_store_true_flag(raw, "--headed")
    args = parser.parse_args(cleaned if raw is not None else None)
    if headed_present:
        args.headed = True
    return args


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parse_cli(argv)
    _setup_logging(args.verbose)
    _setup_langsmith(args.langsmith, headed=getattr(args, "headed", False))

    if not hasattr(args, "func"):
        build_parser().print_help()
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