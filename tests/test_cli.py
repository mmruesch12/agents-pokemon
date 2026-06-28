"""Tests for CLI argument parsing."""

from __future__ import annotations

import pytest

from src.run.autonomous_runner import build_parser as runner_parser
from src.run.cli import build_parser


def test_cli_help_flags():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_cli_rom_and_steps():
    parser = build_parser()
    args = parser.parse_args(["--rom", "roms/test.gb", "--steps", "100"])
    assert args.rom == "roms/test.gb"
    assert args.steps == 100


def test_cli_langsmith_flag():
    parser = build_parser()
    args = parser.parse_args(["--langsmith"])
    assert args.langsmith is True


def test_runner_max_steps_zero():
    parser = runner_parser()
    args = parser.parse_args(["--max-steps", "0"])
    assert args.max_steps == 0


def test_runner_resume_flag():
    parser = runner_parser()
    args = parser.parse_args(["--resume", "latest"])
    assert args.resume == "latest"


def test_cli_headed_flag():
    """--headed enables visible window (not default)."""
    parser = build_parser()
    args = parser.parse_args(["--headed", "--steps", "10"])
    assert args.headed is True
    args2 = parser.parse_args(["--steps", "10"])
    assert getattr(args2, "headed", False) is False


def test_runner_headed_flag():
    """Runner parser --headed and default headless."""
    parser = runner_parser()
    args = parser.parse_args(["--headed", "--max-steps", "10"])
    assert args.headed is True
    args2 = parser.parse_args(["--max-steps", "10"])
    assert getattr(args2, "headed", False) is False


def test_cli_headed_works_after_subcommand():
    """--headed works after sub (run/resume) for easy UX."""
    parser = build_parser()
    a = parser.parse_args(["run", "--headed", "--steps", "42"])
    assert a.headed is True
    assert a.steps == 42
    a2 = parser.parse_args(["resume", "--headed"])
    assert a2.headed is True
    assert a2.resume == "latest"


@pytest.mark.parametrize(
    "argv,expected_steps",
    [
        (["--headed", "--steps", "10"], 10),
        (["run", "--headed", "--steps", "10"], 10),
        (["--headed", "run", "--steps", "10"], 10),
    ],
)
def test_cli_headed_any_position(argv, expected_steps):
    """--headed is honored in any position (pre-sub, post-sub, pre+sub)."""
    from src.run.cli import _parse_cli
    a = _parse_cli(argv)
    assert a.headed is True
    # the namespace is the one passed to cmd_run / runner
    assert a.steps == expected_steps