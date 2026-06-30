"""poke-watch: easy headed viewer — forces --headed and --resume latest by default."""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from src.run.cli import _parse_cli, _setup_langsmith, _setup_logging, build_parser, cmd_run


def _fast_start_skips_resume(argv: list[str]) -> bool:
    """Fast-start snapshots are incompatible with --resume (fresh state each run)."""
    return any(
        flag in argv
        for flag in ("--start-bedroom", "--start-lab", "--emulator-state")
    ) or any(tok.startswith("--emulator-state=") for tok in argv)


def normalize_watch_argv(argv: list[str]) -> list[str]:
    """Inject --headed and --resume latest unless --no-resume or a fast-start flag."""
    no_resume = False
    cleaned: list[str] = []
    for tok in argv:
        if tok == "--no-resume":
            no_resume = True
            continue
        cleaned.append(tok)
    if "--headed" not in cleaned:
        cleaned.insert(0, "--headed")
    has_resume = any(t == "--resume" or t.startswith("--resume=") for t in cleaned)
    if not no_resume and not _fast_start_skips_resume(cleaned) and not has_resume:
        cleaned = ["--resume", "latest", *cleaned]
    return cleaned


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    watch_argv = normalize_watch_argv(list(argv if argv is not None else sys.argv[1:]))
    args = _parse_cli(watch_argv)
    args.headed = True
    _setup_logging(args.verbose)
    _setup_langsmith(args.langsmith, headed=True)

    if not hasattr(args, "func"):
        build_parser().print_help()
        return 0

    try:
        return cmd_run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())