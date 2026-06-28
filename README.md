# Pokemon Gold Agent

Autonomous multi-agent Pokemon Gold/Silver (Gen 2) player using PyBoy + LangGraph + LangSmith.

## Disclaimer

This project is an independent experiment and is **not affiliated with, endorsed by, or sponsored by Nintendo or The Pokemon Company**.

- **No game ROM is included.** You must supply your own legal dump of Pokemon Gold or Silver.
- Do not commit ROM files, API keys, or runtime data (`roms/*.gb`, `.env`, `data/`, `saves/`).
- Pokemon names and game data references are used for interoperability with user-provided ROMs.

## Features

- **Emulator Control Plane**: PyBoy wrapper (headless by default; --headed for visible SDL2 window) with save/load states
- **Structured Perception**: Gen 2 RAM parsers producing rich `GameState`
- **Multi-Agent Graph**: Supervisor, Planner, Navigator, Battler, Critic, Memory Manager
- **Persistence**: SQLite checkpointer + emulator save states for pause/resume
- **Evaluation**: Progress, stuck frequency, and coherence metrics
- **LangSmith**: Full tracing support

## Quick Start

```bash
# After `uv sync`, placing your ROM, and editing `.env`
uv run python -m src.run.verify_setup

# Run the agent (headless by default)
uv run python -m src.run.cli --steps 500                 # short / dev run
uv run python -m src.run.autonomous_runner --max-steps 5000 --resume latest

# Watch the agent play (visible SDL2 window)
uv run poke-watch --steps 120 -v
uv run poke-runner --headed --max-steps 150
uv run poke-agent --headed --steps 200
uv run python -m src.run.cli --headed --steps 200
```

Using --headed enables a visible emulator window (headless by default; use --headed to watch the agent play). The poke-* entry points work out of the box after `uv sync`.

**Simplest way to watch:** `uv run poke-watch` (headed + resume latest by default; pass `--steps N` to limit). The SDL2 window will appear on your desktop.

**Note on boot/intro:** Even the title screen + naming/clock dialogs are not instant. A cold boot does an upfront frame wait (fast-forwarded in code) followed by ~dozens of individual button presses. Each press during the graph phase of bootstrap goes through the full supervisor/bootstrap/apply/critic/memory cycle + checkpoint. This creates pauses between inputs even though no LLM is involved.

### Why does the game feel "laggy" or slow when watching?
The agent is an LLM-driven multi-agent system (supervisor → planner/navigator → apply action → critic → memory).  
Every movement decision typically requires 1+ remote LLM calls (via xAI Grok, OpenRouter or OpenAI). Even fast models introduce multi-second pauses between visible actions while the agent "thinks".

During actual button presses the emulator runs at normal speed (especially nice in headed mode). The pauses are expected agent behavior, not a bug. For faster experimentation you can:
- Use a faster model via env `XAI_MODEL=...`
- Run headless for long training sessions
- Use small `--steps` values when watching

Press Ctrl-C in the terminal (or close the window) to stop.

Other commands:
```bash
uv run python -m src.run.cli eval --dataset early_game   # evaluators
uv run pytest tests/ -q                                  # tests (no ROM needed)
```

## Setup (Ubuntu/Debian)

```bash
# System dependencies
sudo apt update
sudo apt install -y libsdl2-dev build-essential python3-dev git tmux

# Project
cd agents-pokemon
uv sync

# ROM (user-provided legal dump)
mkdir -p roms saves data
cp /path/to/pokemon_gold.gb roms/pokemon_gold.gb

# Environment
cp .env.example .env
# Edit .env: XAI_API_KEY or OPENROUTER_API_KEY or OPENAI_API_KEY, LANGSMITH_API_KEY, ROM_PATH
```

## Architecture

```
[PyBoy Emulator] → RAM Parsers → GameState
                        ↓
[LangGraph] ← Tools (get_state, press_button, navigate, battle_decide)
  Supervisor → Planner → Navigator/Battler → Critic → Memory
                        ↓
[LangSmith] + [Checkpoints] + [Save States]
```

## Project Structure

```
src/
├── emulator/     # PyBoy wrapper, headless runner
├── state/        # GameState models, GoldStateReader
├── tools/        # LangChain @tool wrappers
├── graph/        # AgentState, nodes, router, pathfinding
├── memory/       # Long-term memory summaries + facts
├── eval/         # Datasets and evaluators
└── run/          # CLI and autonomous runner
```

See [spec.md](spec.md) for the full design document. AI agents: read [AGENTS.md](AGENTS.md) first.

## License

MIT — see [LICENSE](LICENSE).