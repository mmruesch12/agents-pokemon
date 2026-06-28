# AGENTS.md — Pokemon Gold Agent

Guidelines for AI coding agents working in this repository.

## Security — read this first

**Never commit secrets, credentials, or user-private data.** This repo is public.

### Do not commit

| Category | Examples | Notes |
|----------|----------|-------|
| API keys & tokens | `XAI_API_KEY`, `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `gho_*`, `sk-*`, `xai-*`, `lsv2_pt_*` | Use `.env` only (gitignored) |
| Environment files | `.env`, `.env.local`, `.env.production` | Copy from `.env.example` with empty placeholders |
| Game ROMs | `roms/*` (`.gb`, `.gbc`, `.zip`, etc.) | User must supply their own legal dump |
| Runtime data | `data/*` (except `.gitkeep`), `saves/*`, `*.sqlite`, `data/chroma/`, `data/faiss/` | Checkpoints, memory, emulator saves |
| Virtualenv / caches | `.venv/`, `__pycache__/`, `.pytest_cache/` | Local tooling only |

### Before every commit

1. Run `git status` and inspect staged files.
2. Run `git diff --cached` and scan for key-like strings (`xai-`, `sk-`, `lsv2_pt_`, `gho_`, `Bearer `).
3. If you created or edited `.env`, confirm it is **not** staged.
4. Never paste real API keys into source, tests, docs, commit messages, or PR descriptions.
5. Never copy keys from other projects on disk into tracked files — only into local `.env`.
6. If a secret was committed, tell the user immediately; do not push. Rotate the exposed key.

### Safe patterns

- Read secrets from `os.getenv(...)` or `load_dotenv()` at runtime.
- Log whether keys are `set` or `missing`, never their values (see `src/run/verify_setup.py`).
- Use fake placeholders in tests (`xai-test-key`, empty strings in `.env.example`).
- Keep `.env.example` keys empty; document variable names only.

---

## Project overview

Autonomous multi-agent Pokemon Gold/Silver player:

- **PyBoy** — headless emulator control plane
- **LangGraph** — Supervisor → Planner → Navigator/Battler → Critic → Memory
- **LangSmith** — optional tracing
- **OpenRouter** (default), **xAI Grok**, or **OpenAI** — LLM for planner/navigator/battler nodes

Design spec: [spec.md](spec.md)

## Project structure

```
src/
├── emulator/     # PyBoyWrapper, headless_runner, smoke_test_rom
├── state/        # GameState models, GoldStateReader (Gen 2 WRAM)
├── tools/        # LangChain @tool wrappers (bind_emulator / unbind_emulator)
├── graph/        # AgentState, nodes, router, pathfinding, llm
├── memory/       # LongTermMemory (local JSON + optional FAISS)
├── eval/         # Datasets and evaluators
└── run/          # cli, autonomous_runner, verify_setup
tests/            # ROM-free tests; MutableRamEmulator for graph integration
```

## How to run

```bash
uv sync                                          # install deps
uv run python -m src.run.verify_setup            # check env, LLM, PyBoy, ROM

# Run the agent (headless by default)
uv run python -m src.run.cli --steps 500
uv run python -m src.run.autonomous_runner --resume latest --max-steps 5000

# Shorter entry points (python -m and poke-* both work after `uv sync`)
uv run python -m src.run.cli --steps 500
uv run python -m src.run.autonomous_runner --resume latest --max-steps 5000
uv run poke-agent --steps 500
uv run poke-runner --resume latest --max-steps 5000

# Headed mode: watch visible PyBoy window while agent plays (not default)
uv run python -m src.run.cli --headed --steps 200
uv run python -m src.run.autonomous_runner --headed --resume latest --max-steps 1000

uv run pytest tests/ -q                          # run tests (expect ~60+)
```

System deps (Ubuntu): `libsdl2-dev`, `build-essential`, `python3-dev`

## Coding conventions

- Python 3.12+, 4-space indentation
- `snake_case` modules/functions; `PascalCase` classes
- Pydantic models in `src/state/models.py`; graph state in `src/graph/state.py`
- Prefer extending existing nodes/tools over new parallel abstractions
- Match existing patterns: heuristic fallback when LLM unavailable, per-step `run_max_steps` in runner

## Testing

- **No ROM required** for CI — use `tests/fake_emulator.py` (`MutableRamEmulator`) and `ByteArrayReader` fixtures in `tests/conftest.py`
- Monkeypatch `OPENROUTER_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY` in LLM fallback tests
- Add tests for graph routing, stuck detection, and RAM parsing when changing those layers
- Optional live ROM smoke: `@pytest.mark.rom` (not in default suite)

## Graph behavior (do not break casually)

- One macro-step per outer `invoke()` — runner sets `run_max_steps = current_steps + 1`
- Flow: specialist → `apply_action` → `critic` → `memory` → supervisor
- Stuck meter updates in `apply_action_node` by comparing position before/after move
- `OPENROUTER_API_KEY` is preferred (first) in `src/graph/llm.py`, then XAI, then OpenAI

## Commit guidelines

- Short imperative subjects (e.g. `Fix stuck meter on no-op navigation`)
- Keep commits focused; do not mix refactors with behavior fixes
- Never commit `.env`, ROMs, sqlite checkpoints, or `data/` runtime files
- PRs should include test command + result

## Legal / content

- **No Nintendo ROM** in the repo — README disclaimer applies
- Pokemon names in code are for interoperability with user-provided ROMs only
- Do not add ROM download instructions or links to pirated content

## Common pitfalls

- `bind_emulator()` is global — tests use autouse `unbind_emulator` fixture in `conftest.py`
- `data/*` is gitignored — memory JSON and checkpoints stay local
- RAM offsets must match pret/pokegold; validate with real ROM when changing `gold_state_reader.py`
- Making repo public again: re-run secret scan on `git log -p` if unsure