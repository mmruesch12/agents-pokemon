"""Tests for CLI argument parsing."""

from __future__ import annotations

from src.run.autonomous_runner import build_parser as runner_parser
from src.run.cli import build_parser


def test_cli_help_flags():
    import pytest

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