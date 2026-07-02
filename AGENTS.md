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

- **PyBoy** — headless emulator control plane (headed watch via owner-thread queue)
- **LangGraph** — Supervisor → specialists → apply_action → Critic → Memory → Supervisor
- **LangSmith** — optional tracing (`--langsmith`; off by default in headed/watch)
- **OpenRouter** (preferred/default when its key is set), **xAI Grok**, or **OpenAI** — LLM for planner/navigator/battler nodes
- **Phases** — `house_exit` and `starter_quest` modules delegate early-game routing, milestones, and targets

Design spec: [spec.md](spec.md) (original 2026-06 design; see README for current CLI). Graph mental model: [docs/agent-mental-model.html](docs/agent-mental-model.html).

## Operating philosophy

The agent should be **minimally prescriptive and strongly self-correcting**. Prefer generic policies that work across maps and quests over tile-specific scripts.

| Principle | Where it lives | What it means |
|-----------|----------------|---------------|
| ROM-signal routing | `generic_interact.py`, supervisor | Route to interactor when WRAM/script state expects dialog input — not because a phase guessed an `(x,y)` |
| Self-correction first | `nodes.py` (M3/M4/M11), `generic_interact.py` | Fix stuck loops with pocket-stuck tracking, pure-nav oscillation detection, at-target blocked-ahead interact, and critic replan **before** adding coordinate rules |
| Generic over tile scripts | `generic_interact.py`, `nodes.py`, `pathfinding.py` | Recovery logic belongs in graph layers testable with `MutableRamEmulator`; avoid new `(x,y)` routing tables in `phases/` |
| Shrink phases | `src/graph/phases/` | Phases should trend toward milestone checkers and landmark seeding, not scripted step lists — see [docs/autonomous-agent-roadmap.md](docs/autonomous-agent-roadmap.md) |
| Prescription budget | PR review habit | Each new hard-coded coordinate or map-specific branch needs a justification: why generic self-correction could not solve it |

When the agent ping-pongs in a small area, assume the stuck meter or critic failed — extend M3/M11/M4, not the phase module.

## Documentation map

| Doc | When to read |
|-----|----------------|
| [README.md](README.md) | Human quick start, watch mode, setup, architecture overview |
| [AGENTS.md](AGENTS.md) | Security, conventions, graph invariants, pitfalls (this file) |
| [spec.md](spec.md) | Original phased design; Sections 4–9 are historical, not a live checklist |
| [docs/agent-mental-model.html](docs/agent-mental-model.html) | Interactive graph flow, routing priority, LLM call sites, phase flags |
| [docs/future-headed-optimizations.md](docs/future-headed-optimizations.md) | Headed/watch profile: MemorySaver, owner thread, resume behavior |
| [docs/memory-analysis.md](docs/memory-analysis.md) | Memory layers, utilization gaps, improvement ideas |
| [docs/house-exit-autonomy-analysis.md](docs/house-exit-autonomy-analysis.md) | How house-exit phase was built; scalability lessons |
| [docs/early-game-elm-lab-proposal.md](docs/early-game-elm-lab-proposal.md) | Starter-quest design record (`starter_quest` phase) |
| [docs/watch-ui-ideas.md](docs/watch-ui-ideas.md) | Watch/HUD options; web dashboard marked implemented |
| [dashboard/README.md](dashboard/README.md) | React dashboard build, API endpoints, dev scripts |

**Doc drift checks:** `uv run pytest -q -k "doc or headed"`; grep tracked `*.md` for outdated setup commands (manual pip bootstrap, wrong test counts).

## Project structure

```
src/
├── emulator/     # PyBoyWrapper, headless_runner, bootstrap, smoke_test_rom
├── state/        # GameState models, GoldStateReader (Gen 2 WRAM), script_constants
├── tools/        # LangChain @tool wrappers (bind_emulator / unbind_emulator)
├── graph/        # AgentState, nodes, router, pathfinding, llm, phases/
├── memory/       # LongTermMemory (local JSON + optional FAISS)
├── eval/         # Datasets and evaluators
└── run/          # cli, autonomous_runner, watch, dashboard_server, verify_setup
dashboard/        # React UI (build → dist/); served by dashboard_server
tests/            # ROM-free tests; MutableRamEmulator for graph integration
docs/             # Analysis, proposals, headed-mode notes, agent mental model
```

## How to run

```bash
uv sync                                          # install deps
uv run python -m src.run.verify_setup            # check env, LLM, PyBoy, ROM

# Run the agent (headless by default)
uv run python -m src.run.cli --steps 500
uv run python -m src.run.autonomous_runner --resume latest --max-steps 5000

# Shorter entry points (python -m and poke-* both work after `uv sync`)
uv run poke-agent --steps 500
uv run poke-runner --resume latest --max-steps 5000
uv run poke-watch --steps 120                    # headed + --resume latest by default

# Subcommands (also via poke-agent)
uv run poke-agent eval --dataset early_game
uv run poke-agent dashboard --port 8765          # React UI + /api/state (build dashboard/ first)
uv run poke-agent traces --limit 10              # LangSmith trace listing (needs LANGSMITH_API_KEY)

# Headed mode: watch visible PyBoy window while agent plays (not default)
uv run python -m src.run.cli --headed --steps 200
uv run python -m src.run.autonomous_runner --headed --resume latest --max-steps 1000

# Fast bedroom start (skips title + graph bootstrap for early-game iteration)
uv run python -m src.run.cli --start-bedroom --steps 200
uv run poke-watch --start-bedroom --steps 500   # headed; resume skipped

uv run pytest tests/ -q                          # run tests (expect ~352)
```

System deps (Ubuntu): `libsdl2-dev`, `build-essential`, `python3-dev`

## Coding conventions

- Python 3.12+, 4-space indentation
- `snake_case` modules/functions; `PascalCase` classes
- Pydantic models in `src/state/models.py`; graph state in `src/graph/state.py`
- Prefer extending existing nodes/tools over new parallel abstractions
- Match existing patterns: heuristic fallback when LLM unavailable, per-step `run_max_steps` in runner
- Early-game logic belongs in `src/graph/phases/` — keep `nodes.py` as thin delegates

## Testing

- **No ROM required** for CI — use `tests/fake_emulator.py` (`MutableRamEmulator`) and `ByteArrayReader` fixtures in `tests/conftest.py`
- Monkeypatch `OPENROUTER_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY` in LLM fallback tests
- Add tests for graph routing, stuck detection, and RAM parsing when changing those layers
- Doc consistency: `tests/test_doc_headed_profile.py` asserts headed-mode notes in `docs/future-headed-optimizations.md`
- Doc drift check (local): `uv run pytest -q -k "doc or headed"`; grep tracked docs for outdated setup commands and wrong test counts
- Optional live ROM smoke: `@pytest.mark.rom` (not in default suite)

## Graph behavior (do not break casually)

- One macro-step per outer `invoke()` — runner sets `run_max_steps = current_steps + 1`
- Flow: **supervisor** → specialist (`bootstrap` | `planner` | `navigator` | `interactor` | `battler` | `waiter` | `idle`) → **`apply_action`** → **`critic`** → **`memory`** → supervisor (or **END** when `run_max_steps` reached)
- Supervisor routing uses game signals (`needs_bootstrap`, script wait, interaction, battle) and phase satisfaction (`house_exit`, `starter_quest` via `_hold_phase_satisfied`)
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
- `data/*` is gitignored — memory JSON, watch snapshots, and checkpoints stay local
- RAM offsets must match pret/pokegold; validate with real ROM when changing `gold_state_reader.py`
- **Headed/watch profile:** `MemorySaver` (in-proc) instead of sqlite; `_resolve_thread_id("latest")` peeks sqlite only when **not** headed; LangSmith off unless `--langsmith` (see `docs/future-headed-optimizations.md`)
- `--start-bedroom` is incompatible with `--resume` (fresh bedroom state each run)
- Dashboard needs `cd dashboard && npm run build` before `poke-agent dashboard` serves the React UI
- If untracked WIP `.py` files appear under `src/` or `tests/` after local runs, they are **not shipped** — run `git checkout HEAD -- src/ tests/` and delete orphans before committing