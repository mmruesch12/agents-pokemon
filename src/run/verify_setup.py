"""Verify local setup: env keys, LLM ping, PyBoy, ROM."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    root = Path(__file__).resolve().parents[2]
    rom = Path(os.getenv("ROM_PATH", "roms/pokemon_gold.gb"))
    if not rom.is_absolute():
        rom = root / rom

    print("=== Pokemon Gold Agent — setup check ===")
    print(f"Project: {root}")
    print(f"ROM path: {rom} ({'found' if rom.exists() else 'MISSING'})")

    openrouter = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    xai = bool(os.getenv("XAI_API_KEY", "").strip())
    openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
    langsmith = bool(os.getenv("LANGSMITH_API_KEY", "").strip())
    print(f"OPENROUTER_API_KEY: {'set' if openrouter else 'missing'}")
    print(f"XAI_API_KEY: {'set' if xai else 'missing'}")
    print(f"OPENAI_API_KEY: {'set' if openai else 'missing'}")
    print(f"LANGSMITH_API_KEY: {'set' if langsmith else 'missing'}")

    from src.graph.llm import get_chat_model

    llm = get_chat_model()
    if llm is None:
        print("LLM: unavailable (heuristic-only mode)")
        if not openrouter:
            print("  Tip: OpenRouter is the preferred provider. Set OPENROUTER_API_KEY in .env to use it by default.")
    else:
        from langchain_core.messages import HumanMessage

        try:
            resp = llm.invoke([HumanMessage(content="Reply with one word: ok")])
            ping = resp.content.strip()[:40]
        except Exception as exc:
            ping = f"configured (ping failed: {type(exc).__name__})"
        # Determine provider label for clarity
        if openrouter:
            provider = "OpenRouter (default)"
        elif xai:
            provider = "xAI"
        else:
            provider = "OpenAI"
        print(f"LLM: {provider} — model={llm.model_name} — ping: {ping}")

    default_pyboy_rom = None
    cache_root = Path.home() / ".cache" / "uv"
    if cache_root.exists():
        for candidate in cache_root.rglob("pyboy/default_rom.gb"):
            default_pyboy_rom = candidate
            break
    if default_pyboy_rom:
        from src.emulator.headless_runner import smoke_test_rom

        result = smoke_test_rom(default_pyboy_rom, frames=30)
        print(f"PyBoy smoke (bundled test ROM): {result}")
    else:
        print("PyBoy smoke: skipped (bundled default_rom.gb not found)")

    if not rom.exists():
        print("\nNo Pokemon ROM found. Place a legal dump at roms/pokemon_gold.gb")
        print("PyBoy works, but the agent cannot play Pokemon without your ROM.")
        return 1

    from src.emulator.headless_runner import smoke_test_rom

    poke = smoke_test_rom(rom, frames=60)
    print(f"Pokemon ROM smoke: {poke}")
    return 0


if __name__ == "__main__":
    sys.exit(main())