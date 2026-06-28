"""Central LangSmith / tracing configuration for CLI and runners."""

from __future__ import annotations

import os


def configure_tracing(*, langsmith: bool, headed: bool = False) -> None:
    """Enable or disable LangChain tracing for a run profile."""
    if langsmith:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "pokemon-gold-agent")
    elif headed:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"