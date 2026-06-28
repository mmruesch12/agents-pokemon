"""Central LangSmith / tracing configuration for CLI and runners."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from src.graph.state import AgentState


def configure_tracing(*, langsmith: bool, headed: bool = False) -> None:
    """Enable or disable LangChain tracing for a run profile."""
    if langsmith:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "pokemon-gold-agent")
        # Ensure full inputs/outputs/metadata are sent (not redacted).
        os.environ.setdefault("LANGSMITH_HIDE_INPUTS", "false")
        os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS", "false")
        os.environ.setdefault("LANGSMITH_HIDE_METADATA", "false")
    elif headed:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"


def _trace_summary(state: AgentState) -> dict[str, Any]:
    """Compact per-step fields for LangSmith metadata (full state still in run IO)."""
    gs = state.get("game_state", {})
    player = gs.get("player", {})
    battle = gs.get("battle", {})
    metrics = state.get("metrics", {})
    return {
        "step": metrics.get("steps", 0),
        "phase": state.get("phase", ""),
        "next_node": state.get("next_node", ""),
        "last_action": state.get("last_action", ""),
        "active_subgoal": state.get("active_subgoal", ""),
        "critic_verdict": state.get("critic_verdict", ""),
        "stuck_count": state.get("stuck_count", 0),
        "map_name": player.get("map_name", ""),
        "position": f"({player.get('x', '?')},{player.get('y', '?')})",
        "in_battle": battle.get("in_battle", False),
        "badges": gs.get("total_badges", metrics.get("badges_earned", 0)),
        "milestones": state.get("milestones", []),
    }


def build_invoke_config(
    state: AgentState,
    *,
    thread_id: str,
    headed: bool = False,
) -> dict[str, Any]:
    """RunnableConfig with rich metadata/tags for LangSmith trace inspection."""
    summary = _trace_summary(state)
    step = summary["step"]
    phase = summary["phase"] or "unknown"
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": f"step-{step}-{phase}",
        "tags": [
            "pokemon-gold-agent",
            f"step-{step}",
            f"phase-{phase}",
            "headed" if headed else "headless",
        ],
        "metadata": {
            "thread_id": thread_id,
            "headed": headed,
            **summary,
        },
    }


def trace_project_name() -> str:
    return os.environ.get("LANGSMITH_PROJECT", "pokemon-gold-agent")


def trace_ui_url() -> str:
    return f"https://smith.langchain.com/o/default/projects/p/{trace_project_name()}"


def run_langsmith_cli(argv: list[str]) -> int:
    """Invoke the langsmith CLI (falls back to a clear error if missing)."""
    try:
        proc = subprocess.run(["langsmith", *argv], check=False)
        return proc.returncode
    except FileNotFoundError:
        print(
            "langsmith CLI not found. Install: curl -fsSL https://cli.langsmith.com/install.sh | sh",
            file=sys.stderr,
        )
        return 127


def format_trace_run(run: dict[str, Any], *, indent: int = 0) -> list[str]:
    """Pretty-print one run with inputs/outputs for terminal inspection."""
    prefix = "  " * indent
    latency = run.get("latency")
    if latency is None and run.get("duration_ms") is not None:
        latency = (run.get("duration_ms") or 0) / 1000
    latency_label = f"{int((latency or 0) * 1000)}ms" if latency is not None else "?"
    lines = [
        f"{prefix}{run.get('name', '?')} ({run.get('run_type', '?')}) "
        f"[{run.get('status', '?')}, {latency_label}]"
    ]
    if run.get("error"):
        lines.append(f"{prefix}  error: {run['error']}")
    for field in ("inputs", "outputs"):
        value = run.get(field)
        if value:
            payload = json.dumps(value, indent=2, default=str)
            if len(payload) > 2000:
                payload = payload[:2000] + "\n  ... (truncated)"
            lines.append(f"{prefix}  {field}:")
            for pline in payload.splitlines():
                lines.append(f"{prefix}    {pline}")
    return lines


def fetch_trace_details(
    trace_id: str,
    *,
    project: str | None = None,
) -> dict[str, Any]:
    """Fetch a trace and all child runs with full IO via the LangSmith SDK."""
    from langsmith import Client

    project = project or trace_project_name()
    client = Client()
    root = client.read_run(trace_id)
    children = list(
        client.list_runs(
            project_name=project,
            trace_id=trace_id,
            limit=100,
        )
    )

    def _as_dict(run: Any) -> dict[str, Any]:
        if hasattr(run, "model_dump"):
            return run.model_dump()
        if hasattr(run, "dict"):
            return run.dict()
        return dict(run)

    return {
        "trace_id": trace_id,
        "project": project,
        "root": _as_dict(root),
        "runs": [_as_dict(r) for r in children],
    }