"""Tests for CLI argument parsing."""

from __future__ import annotations

import pytest

from src.run.autonomous_runner import build_parser as runner_parser
from src.run.cli import build_parser
from src.run.watch import normalize_watch_argv


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
    assert args.resume is None


def test_cli_default_run_does_not_implicitly_resume():
    from src.run.cli import _parse_cli

    args = _parse_cli(["--steps", "10", "--thread-id", "fresh"])
    assert args.resume is None
    assert args.thread_id == "fresh"


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
    assert a2.func.__name__ == "cmd_resume"


def test_watch_normalizes_headed_and_resume_latest():
    argv = normalize_watch_argv(["--steps", "120"])
    assert argv[0:4] == ["--resume", "latest", "--headed", "--steps"]
    assert argv[4] == "120"


def test_watch_no_resume_skips_resume_flag():
    argv = normalize_watch_argv(["--no-resume", "--steps", "50"])
    assert "--resume" not in argv
    assert argv[0] == "--headed"


def test_cli_start_bedroom_flag():
    parser = build_parser()
    args = parser.parse_args(["--start-bedroom", "--steps", "200"])
    assert args.start_bedroom is True
    assert args.resume is None


def test_parse_cli_start_bedroom_pre_subcommand():
    """--start-bedroom before subcommand must be recognized (via pop)."""
    from src.run.cli import _parse_cli

    args = _parse_cli(["--start-bedroom", "run", "--steps", "50"])
    assert args.start_bedroom is True
    assert args.steps == 50

    args2 = _parse_cli(["--start-bedroom", "--steps", "123"])
    assert args2.start_bedroom is True


def test_runner_start_bedroom_flag():
    parser = runner_parser()
    args = parser.parse_args(["--start-bedroom", "--max-steps", "200"])
    assert args.start_bedroom is True


def test_watch_start_bedroom_skips_resume():
    argv = normalize_watch_argv(["--start-bedroom", "--steps", "120"])
    assert "--resume" not in argv
    assert "--start-bedroom" in argv


def test_watch_start_lab_skips_resume():
    argv = normalize_watch_argv(["--start-lab", "--steps", "120"])
    assert "--resume" not in argv
    assert "--start-lab" in argv
    assert argv[0] == "--headed"


def test_start_bedroom_rejects_resume():
    from src.run.autonomous_runner import AutonomousRunner

    runner = AutonomousRunner(
        rom_path="roms/pokemon_gold.gb",
        max_steps=10,
        start_bedroom=True,
    )
    import pytest

    with pytest.raises(ValueError, match="Fast-start"):
        runner.run(resume="latest")


def test_cli_start_lab_flag():
    parser = build_parser()
    args = parser.parse_args(["--start-lab", "--steps", "120"])
    assert args.start_lab is True


def test_cli_emulator_state_flag():
    parser = build_parser()
    args = parser.parse_args(["--emulator-state", "stuck_198", "--steps", "50"])
    assert args.emulator_state == "stuck_198"


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