# High-Level Specification: Autonomous Multi-Agent Pokémon Gold/Silver Player

**Project Name**: `pokemon-gold-agent` (or `poke-langgraph-agent`)  
**Goal**: Build a fun, observable, long-running autonomous agent system that plays Pokémon Gold/Silver (Gen 2) from a new game toward meaningful progress (e.g., first few gyms or further) using PyBoy + LangGraph + LangSmith.  
**Primary Purpose**: Experiment with and validate professional-grade multi-agent orchestration patterns (supervisor, hierarchical planning, specialist agents, critic/reflection, memory) in a rich, visual, long-horizon environment.  
**Secondary Purpose**: Create a reusable "Pokémon Control Plane" (MCP-like API + structured state) that any agent framework can drive.  
**Target Environment**: Linux machine (Ubuntu/Debian recommended; tested patterns apply to WSL too). Headless-capable for background runs.  
**Timeline Expectation**: Phase 0–2 in 1–2 focused weekends; full autonomous runs + iteration over weeks/months as a pet project.  
**Success Criteria**:
- Reliable navigation and basic progression (reach first gym with low stuck rate).
- Clean, traceable multi-agent runs in LangSmith.
- Measurable improvement via evals (progress per steps, stuck frequency, coherence).
- Ability to pause/resume long sessions cleanly.
- Reusable components for future agent experiments.

---

## 1. High-Level Architecture

### Layered Design (Separation of Concerns)
1. **Emulator Control Plane** ("MCP layer")
   - PyBoy wrapper (headless, fast emulation, button control, frame advance, save/load states).
   - Game-specific RAM parsers → rich structured `GameState`.
   - High-level tools (navigate, battle actions, menu interactions) + low-level primitives.
   - Optional: FastAPI server + WebSocket + simple dashboard (inspired by NousResearch/pokemon-agent).

2. **LangGraph Agent Orchestration Layer**
   - Stateful `StateGraph` with rich `AgentState`.
   - Multi-agent nodes: Supervisor, Planner, Navigator, Battler, Critic/Reflector, Memory Manager.
   - Hierarchical planning + conditional routing.
   - Tools bound to Control Plane.
   - Persistence via LangGraph checkpointers + emulator save states.

3. **Observability & Evaluation Layer**
   - LangSmith: Full tracing, datasets, custom evaluators, progress metrics.
   - Optional live dashboard (reasoning stream, game state viz, stuck meter, milestones).
   - Logging + milestone notifications.

4. **Persistence & Runtime Layer**
   - Emulator save states + LangGraph checkpoints.
   - Long-term memory (vector store summaries + structured facts).
   - Background/long-running harness (tmux, systemd, or simple loop with resume).

**Data Flow**:
```
[PyBoy Emulator] → RAM Parsers → Structured GameState
                          ↓
[LangGraph Graph] ← Tools (get_state, execute_action, pathfind, etc.)
   (Supervisor → Planner → Specialists → Critic → Memory)
                          ↓
[LangSmith Traces + Evals] + [Dashboard] + [Save States]
```

---

## 2. Tech Stack & Dependencies (Linux)

**Core**:
- Python 3.11+ (recommend 3.12)
- `pyboy` (emulator)
- `langgraph`, `langchain`, `langsmith` (orchestration + tracing)
- `pydantic` (state models)
- `numpy`, `pillow` (helpers, screenshots if needed)

**Optional but Recommended**:
- `fastapi`, `uvicorn`, `websockets` (control plane server + dashboard)
- `chromadb` or `faiss-cpu` (long-term memory)
- `streamlit` or `gradio` (simple dashboard, alternative to custom)
- `uv` (fast Python package manager) or `poetry`

**System (Linux/Ubuntu)**:
- `libsdl2-dev` (required for PyBoy)
- Build essentials if compiling anything
- `xvfb` (optional, for any SDL2 headless quirks)
- `tmux` or `screen` (for long-running sessions)

**ROM**: User-provided legal dump of Pokémon Gold or Silver (`.gb` or `.gbc`).

**Environment Management**: `uv` + `pyproject.toml` (or venv + requirements.txt). Strongly prefer `uv` for speed and lockfiles.

---

## 3. Core Components & Modules (Proposed Structure)

```
pokemon-gold-agent/
├── pyproject.toml
├── README.md
├── spec.md                          # This file
├── roms/                            # Place your legal ROM here (gitignored)
├── saves/                           # Emulator save states
├── data/                            # Memory stores, datasets, logs
├── src/
│   ├── emulator/
│   │   ├── __init__.py
│   │   ├── pyboy_wrapper.py       # Headless PyBoy instance, button API, tick, save/load
│   │   └── headless_runner.py
│   ├── state/
│   │   ├── __init__.py
│   │   ├── gold_state_reader.py   # RAM parsers using known addresses (Data Crystal + pret/pokegold)
│   │   └── models.py              # Pydantic GameState, PlayerState, PartyMember, etc.
│   ├── tools/
│   │   ├── __init__.py
│   │   └── pokemon_tools.py       # LangChain @tool wrappers (get_state, press_button, navigate, battle_decide, etc.)
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py               # AgentState TypedDict / Pydantic
│   │   ├── nodes.py               # supervisor_node, planner_node, navigator_node, battler_node, critic_node, memory_node
│   │   ├── router.py              # Conditional edges / routing logic
│   │   └── graph.py               # StateGraph assembly + compilation
│   ├── memory/
│   │   ├── __init__.py
│   │   └── long_term_memory.py    # Vector store + summarizer
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── datasets.py
│   │   └── evaluators.py          # Custom progress, stuck, coherence evaluators
│   └── run/
│       ├── __init__.py
│       ├── autonomous_runner.py   # Main loop with checkpoints, stuck handling
│       └── cli.py                 # Entry points (run, resume, eval, dashboard)
├── dashboard/                       # Optional Streamlit/Gradio or extend Nous-style
├── tests/
└── .env.example                     # LANGSMITH_API_KEY, ROM_PATH, etc.
```

**Key Data Models** (high-level):
- `GameState`: player (map, x, y), party (list of Pokémon with species, level, HP, moves, etc.), inventory, badges (bitfield or list), event_flags (set or decoded), in_battle (bool + details), current_objectives, etc.
- `AgentState`: game_state, current_plan (list of goals/subgoals), short_term_history, memory_retrievals, metrics (steps, badges_earned, stuck_count), phase, checkpoint_id, etc.

---

## 4. Implementation Roadmap (Phased)

### Phase 0: Foundations (1–2 days)
- Linux env setup (`uv init`, install `libsdl2-dev`, `pip install pyboy`).
- Basic PyBoy script: load ROM (headless), button presses, `tick()`, memory read, screenshot.
- Project skeleton + `pyproject.toml`.
- Place legal ROM in `roms/`.
- LangSmith project created + API key in `.env`.

### Phase 1: Structured Perception + Simple Agent (3–5 days)
- Implement `GoldStateReader` (start with player map/coords, party count/species/level, basic flags/badges, money).
- `GameState` Pydantic model + `get_game_state()` tool.
- Simple ReAct-style LangGraph agent (or LangChain agent) with tools: `get_state`, `press_button('a'/'up'/etc.)`, `advance_frames(n)`.
- Get agent reliably through New Bark Town → first wild encounter or Pokémon Center.
- Basic LangSmith tracing.

### Phase 2: Multi-Agent Graph + Core Specialists (1–2 weeks)
- Define full `AgentState`.
- Implement nodes: Supervisor (router), Navigator (with visited memory + simple pathfinding), basic Battler.
- Add conditional edges and stuck detection.
- Memory Manager (short-term history + simple vector summaries).
- First LangSmith evaluators (progress per 500 steps, repetition rate).
- Test autonomous loop for 1k–5k steps.

### Phase 3: Critic, Planner, Persistence & Evals (1–2 weeks)
- Add Planner node (hierarchical goal setting).
- Add Critic/Reflector node (post-action review, loop detection, risk veto).
- Full persistence: LangGraph checkpointer (Postgres or SQLite file) + emulator save states.
- Long-running `autonomous_runner.py` with resume, milestone logging, optional notifications.
- Expand evaluators (coherence, battle efficiency, exploration coverage).
- Iterate on stuck handling and navigation (add collision grid + A* if not already).

### Phase 4: Polish, Dashboard & Advanced Features (ongoing)
- Optional FastAPI control plane + dashboard (state viz, reasoning stream, grid overlay).
- Compound actions, better battle logic, Gen 2 specifics (day/night, phone, HM handling).
- Hybrid model routing (frontier for planner/critic, faster model for navigator).
- Public milestone runs + dataset curation from successful traces.
- Documentation + reusable patterns for other games/projects.

---

## 5. Linux Setup Instructions (Ubuntu/Debian)

```bash
# 1. System dependencies
sudo apt update
sudo apt install -y libsdl2-dev build-essential python3-dev git tmux

# Optional for any SDL quirks
sudo apt install -y xvfb

# 2. Project
mkdir ~/projects/pokemon-gold-agent && cd ~/projects/pokemon-gold-agent
uv init --python 3.12
uv add pyboy langgraph langchain langsmith pydantic pillow numpy

# Optional
uv add fastapi uvicorn streamlit chromadb

# 3. ROM
mkdir -p roms saves data
# Copy your legal Pokémon Gold/Silver ROM to roms/pokemon_gold.gb (or .gbc)
# .gitignore roms/ and saves/ and data/

# 4. Environment
cp .env.example .env
# Edit .env: LANGSMITH_API_KEY=..., ROM_PATH=roms/pokemon_gold.gb, etc.

# 5. Verify PyBoy
python -c "
from pyboy import PyBoy
pyboy = PyBoy('roms/pokemon_gold.gb', window='headless')
print('PyBoy loaded successfully')
pyboy.tick(60)
print('Advanced 60 frames')
pyboy.stop()
"
```

**Headless Notes**:
- PyBoy supports `window='headless'` in recent versions.
- If SDL issues appear, wrap runs with `xvfb-run -a python ...`.

**Long-Running**:
- Use `tmux new -s poke-agent` then run your script inside.
- Or create a simple systemd user service for background runs (with auto-restart on failure).
- Always save emulator state + LangGraph checkpoint before exit.

---

## 6. Running the System

**Basic Development Run**:
```bash
uv run python -m src.run.cli --rom roms/pokemon_gold.gb --steps 2000 --langsmith
```

**Autonomous Long-Running**:
```bash
tmux new -s poke-gold
uv run python -m src.run.autonomous_runner --resume latest --max-steps 50000
# Detach with Ctrl+B then D
```

**With Dashboard** (if implemented):
```bash
uv run uvicorn src.emulator.server:app --reload   # or streamlit run dashboard/app.py
```

**Monitoring**:
- LangSmith dashboard for traces, runs, evals.
- Local logs + milestone prints (new badge, area unlocked, stuck events).
- Optional: Simple webhook or email on major milestones or high stuck count.

---

## 7. Key Challenges & Built-in Mitigations (from real projects)

- **Looping / Getting Stuck**: Explicit visited memory + collision grid + Critic node + stuck-meter eval.
- **Long-Horizon Drift**: Hierarchical Planner + periodic reflection + strong memory + goal decomposition.
- **Navigation Precision**: RAM-derived collision + pathfinding tools (not raw buttons).
- **Perception**: Comprehensive `GoldStateReader` (multiple RAM reads + heuristics for menus/battle/text).
- **Cost/Latency**: Hybrid models + compound actions + event-driven (not per-frame) LLM calls.
- **Irreversible Errors**: Frequent save states + Critic veto on risky actions + easy rollback.
- **Gen 2 Complexity**: Leverage pret/pokegold symbols + Data Crystal RAM map; start simple and expand parsers.

---

## 8. Out of Scope (for v1)

- Full game completion guarantee (focus on reliable early-mid game progress + iteration framework).
- Real-time human-competitive speed (focus on correctness + learning first).
- Training/fine-tuning models (use off-the-shelf via LangChain/LiteLLM).
- Multiplayer or competitive battling (single-player RPG focus).

**Future Nice-to-Haves**:
- Integration with NousResearch/pokemon-agent style server (contribute Gold/Silver parsers).
- MCP (Model Context Protocol) server compatibility.
- Hybrid RL + LLM for battle/navigation low-level policies.
- Creative extensions (agent "adventure logs" or story generation from playthroughs).

---

## 9. Next Immediate Actions (Recommended)

1. Set up the Linux environment and verify basic PyBoy + ROM loading (Phase 0).
2. Implement minimal `GoldStateReader` for player position + party (highest leverage).
3. Build the first working ReAct agent that can move and interact reliably.
4. Add LangSmith tracing and create your first simple evaluator.
5. Expand to Supervisor + Navigator graph.

---

**Document Version**: 1.0  
**Date**: 2026-06-26  
**Owner**: Matt Ruesch  
**Status**: High-level spec ready for implementation. Ready to start coding Phase 0.

This spec is intentionally high-level to allow flexibility while providing clear guardrails and a phased path. It directly incorporates lessons from existing PyBoy + LLM Pokémon agent projects (Claude Plays Pokémon, Nous pokemon-agent, open-source repos) and aligns with your goals around multi-agent systems, evaluations, and autonomous long-running agents.

Happy to refine any section, generate the initial `pyproject.toml` + skeleton code, or help with the first Phase 0 script. Just let me know where you want to dive in first!
