"""Tests for LangSmith full-trace configuration and CLI helpers."""

from __future__ import annotations

import os


from src.graph.state import initial_agent_state
from src.run._langsmith import build_invoke_config, configure_tracing, format_trace_run


def test_configure_tracing_enables_full_detail_env(monkeypatch):
    for key in (
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "LANGSMITH_HIDE_METADATA",
    ):
        monkeypatch.delenv(key, raising=False)
    configure_tracing(langsmith=True, headed=False)
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGSMITH_HIDE_INPUTS"] == "false"
    assert os.environ["LANGSMITH_HIDE_OUTPUTS"] == "false"
    assert os.environ["LANGSMITH_HIDE_METADATA"] == "false"


def test_build_invoke_config_includes_step_metadata():
    state = initial_agent_state(
        {
            "player": {"map_name": "Route 29", "x": 10, "y": 20},
            "battle": {"in_battle": False},
            "total_badges": 1,
        }
    )
    state["phase"] = "explore"
    state["last_action"] = "navigate_up"
    state["metrics"] = {"steps": 42}

    config = build_invoke_config(state, thread_id="test-thread", headed=True)

    assert config["configurable"]["thread_id"] == "test-thread"
    assert config["run_name"] == "step-42-explore"
    assert "step-42" in config["tags"]
    assert "headed" in config["tags"]
    assert config["metadata"]["map_name"] == "Route 29"
    assert config["metadata"]["last_action"] == "navigate_up"
    assert config["metadata"]["step"] == 42


def test_format_trace_run_includes_inputs_and_outputs():
    lines = format_trace_run(
        {
            "name": "bootstrap",
            "run_type": "chain",
            "status": "success",
            "duration_ms": 3,
            "inputs": {"last_action": "bootstrap_a"},
            "outputs": {"last_action": "bootstrap_start"},
        }
    )
    text = "\n".join(lines)
    assert "bootstrap" in text
    assert "inputs" in text
    assert "outputs" in text
    assert "bootstrap_a" in text


def test_cli_traces_subcommand_parses():
    from src.run.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["traces", "--trace-id", "abc-123", "--full"])
    assert args.command == "traces"
    assert args.trace_id == "abc-123"
    assert args.full is True
    assert args.func.__name__ == "cmd_traces"