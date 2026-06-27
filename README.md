# Pokemon Gold Agent

Autonomous multi-agent Pokemon Gold/Silver (Gen 2) player using PyBoy + LangGraph + LangSmith.

## Features

- **Emulator Control Plane**: Headless PyBoy wrapper with save/load states
- **Structured Perception**: Gen 2 RAM parsers producing rich `GameState`
- **Multi-Agent Graph**: Supervisor, Planner, Navigator, Battler, Critic, Memory Manager
- **Persistence**: SQLite checkpointer + emulator save states for pause/resume
- **Evaluation**: Progress, stuck frequency, and coherence metrics
- **LangSmith**: Full tracing support

## Setup (Ubuntu/Debian)

```bash
# System dependencies
sudo apt update
sudo apt install -y libsdl2-dev build-essential python3-dev git tmux

# Project
cd pokemon-gold-agent
uv sync

# ROM (user-provided legal dump)
mkdir -p roms saves data
cp /path/to/pokemon_gold.gb roms/pokemon_gold.gb

# Environment
cp .env.example .env
# Edit .env: LANGSMITH_API_KEY, OPENAI_API_KEY, ROM_PATH
```

## Usage

```bash
# Development run
uv run python -m src.run.cli --rom roms/pokemon_gold.gb --steps 2000 --langsmith

# Autonomous long-running
uv run python -m src.run.autonomous_runner --resume latest --max-steps 50000

# Evaluators
uv run python -m src.run.cli eval --dataset early_game

# Tests
uv run python -m pytest tests/ -q
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