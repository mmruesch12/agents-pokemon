# Future Optimizations for Headed / Live Watch Mode

**Status**: Current pragmatic solution implemented (2026-06). This document outlines a cleaner, more optimal long-term architecture that could be integrated later.

**Context / Goal Reminder**
- The visible PyBoy SDL2 window (headed mode) must never randomly pause or freeze due to checkpoint I/O, tracing side-effects, or synchronous long ticks in the main thread.
- `poke-runner --headed` (and `--headed` on `poke-agent` / `cli`) exists so a human can watch the *full autonomous agent* play successfully.
- Headless remains the default and the primary path for long reliable runs.
- Agent success behaviors must never be compromised: supervisor routing, planner/navigator/battler, critic (including bootstrap guards), stuck detection + replan in `apply_action_node` / `critic_node`, memory node, bootstrap flow, `run_max_steps` batching, LangSmith when explicitly enabled, etc.
- See also: [AGENTS.md](../AGENTS.md), `src/run/autonomous_runner.py`, `src/emulator/pyboy_wrapper.py`, `src/graph/graph.py`.

## Current Approach (What Ships Today)

Pragmatic dual-path implementation:

- **Live daemon thread** in `PyBoyWrapper` (`_start_live_thread` / `_live_loop`):
  - For `window != "null"`, a daemon thread continuously calls `tick()` (bursts of 8 during `_ff` fast-forward).
  - `RLock` protects *every* access (`tick`, `press_button`, `get_game_state`, `read_memory_byte`, save/load, screenshot, set_speed).
  - Button holds are scheduled (`_held_key` / `_hold_remaining`) so the live thread does press/release/tick timing; main thread waits briefly.
  - `set_fast_forward()` / `fast_forward()` context accelerates title waits in bootstrap (`run_bootstrap`).
- **MemorySaver instead of SqliteSaver** for headed runs:
  - In `AutonomousRunner.run()`: if `headed` then `MemorySaver()` (in-proc dict) else normal sqlite path.
  - `compile_graph(emu, checkpointer=...)` supports explicit checkpointer.
  - Tracing forced off (`LANGCHAIN_TRACING_V2=false`) unless `--langsmith` explicitly passed.
- **Bootstrap guards**:
  - `critic_node` skips replan/repetition logic for `bootstrap_*` actions.
  - Supervisor and runner force `should_replan=False` while bootstrapping.
  - Bootstrap title wait uses `_ff` fast-forward on the live thread.
- **Simple UX**: `poke-runner --headed --resume latest` (or `poke-agent --headed`) for watch sessions.

**Why it works for the pause problem**
- No `fsync`/disk per graph step → no visible stutter from `SqliteSaver`.
- Background thread keeps SDL2 window pumping frames even while the main thread does routing, state updates, or (when enabled) LLM calls.
- Fast-forward during long title wait hides the 1800-frame blind tick.

**Trade-offs / Complexity (Why We Can Do Better Later)**
- Large amount of `if self._is_live` branching + duplicated logic in `tick`/`press_button`.
- Button-hold scheduling via `_held_key` is still internal to the wrapper.
- Lock held around PyBoy calls; potential for subtle races or deadlocks under load (though `RLock` + daemon helps).
- Approximate hold semantics in live mode (main waits via sleep polling).
- Divergent semantics: headed uses in-memory checkpoint (cross-process `get_state` on resume is a no-op), headless uses persistent sqlite. Resume thread-id logic in `_resolve_thread_id` always peeks sqlite.
- Graph still pays full per-action cost (supervisor → specialist → apply → critic → memory) even for watch sessions; live thread only keeps the window animating during that work.
- Testing live behavior is harder (xvfb + timing-sensitive).
- SDL2/GL context ownership best practices are only partially followed.

Current approach is "good" (achieves the explicit `/goal` of no checkpoint-induced pauses while preserving full agent play) but is a tactical patch rather than a principled design.

## Proposed More Optimal Solution (Target for Later Integration)

### Core Idea: Single-Owner Live Controller + Orthogonal "Observation Profile"

1. **Exclusive-Owner Thread + Command / Future Queue (Clean Threading)**
   - Introduce (or evolve `PyBoyWrapper` into) a `LiveEmulator` / `ThreadedEmulatorClient`.
   - The background thread is the *only* thread that ever touches the raw `PyBoy` instance (creation, tick, button_*, memory[], screen, save/load_state, stop).
   - All operations from the agent / runner / bootstrap are posted as commands to a `queue.Queue` (or `asyncio.Queue` if we ever go async):
     ```python
     Command = tuple  # e.g. ("press", "a", 8), ("tick", 30), ("get_state",), ("read", addr), ("save", path), ...
     ```
   - Responses are delivered via per-command `threading.Event` + result slot, or `concurrent.futures.Future`.
   - Public methods on the wrapper become thin "post and wait with timeout" facades.
   - Benefits:
     - Zero scattered locks or `if _is_live` in hot paths.
     - Proper ownership (important for SDL2 / OpenGL contexts on some platforms).
     - Easier to add rate limiting, metrics, or deterministic replay for tests.
     - `press_button` hold timing becomes exact and owned by the emulator thread.
   - The live loop can stay similar (continuous tick + drain command queue each iteration).

2. **Decouple Persistence from "Headed" Flag**
   - Make checkpointer choice explicit and orthogonal:
     - `AutonomousRunner(..., persist: bool | None = None)`
     - `compile_graph(..., checkpointer=None)` already supports passing one; extend to accept `checkpointer=False` / sentinel meaning "no checkpointer at all" (LangGraph supports `checkpointer=None` meaning no persistence).
   - Headed/watch sets `persist=False` by default (MemorySaver or None).
   - Normal long runs keep sqlite.
   - Provide a sidecar mechanism when `persist=False`:
     - On milestones or every N steps in watch, atomically write `agent_state_<steps>.json` (or pickle) next to the `.state` file.
     - On `--resume latest` in non-persist mode: prefer latest emulator `.state` + matching sidecar to reconstruct `AgentState` (derive `game_state` by re-reading RAM after load, keep high-level plan/history if sidecar present).
   - This removes the current "resume latest" sqlite-peek + MemorySaver mismatch.

3. **Watch / Observation Execution Profile (Reduce Noise Without Changing Agent Logic)**
   - Add `observation_mode: bool` (or derive from `headed and not persist`).
   - In this mode the runner:
     - Uses larger `delta` (or a configurable `batch`).
     - Skips (or makes optional) `evaluate_run` + `memory.summarize_history` every 100 steps (still updates in-memory metrics/milestones).
     - Keeps full critic/stuck/memory nodes — they are cheap and required for correct "the agent plays successfully".
     - Disables LangSmith tracing by default (already done).
     - Can log less verbosely.
   - The *same* compiled graph and node functions are used. No parallel abstractions.
   - Result: fewer Python cycles between visible actions while the agent still makes real decisions, detects stuck, replans, etc.

4. **Bootstrap & Title Path Hardening (Already Partially Done)**
   - Keep the direct `run_bootstrap` fast path + `_ff` acceleration.
   - Under the new queue model, `tick` during ff simply posts many ticks (or a special "ff" command the owner thread handles by running tight without sleep).
   - Bootstrap guards in `supervisor_node` / `critic_node` / runner stay.

5. **Resume + State Files Story**
   - Always produce `.state` files at the same points (end, stuck).
   - For watch/resume-latest, default behavior becomes: load the most recent `.state` into the emulator, seed a fresh-ish `AgentState` from the loaded `GameState`, optionally merge a sidecar if present.
   - Long-running persistent runs continue to use LangGraph sqlite checkpoints for rich "mind" continuity (history, replan_count, active subgoals, short_term_history, etc.).
   - Document that mixing headless and headed across resumes may produce a "mind" reset or partial state; that's acceptable.

6. **API / Packaging Niceties**
   - `PyBoyWrapper(..., live=True)` or constructor chooses the implementation class internally (`SyncEmulator` vs `LiveEmulatorClient`).
   - Expose `emu.set_fast_forward(bool)` cleanly instead of `_ff`.
   - Add a `with emu.live_session(): ...` context if useful.
   - Keep `window=` and `sound=False` behavior exactly.

## Non-Goals (Preserve)

- Do **not** bypass the graph for normal watch sessions (the point of headed watch is watching the *agent*).
- Do **not** remove SqliteSaver / checkpointers from the default path.
- Do **not** change the one-macro-step `run_max_steps` contract in the runner for headless.
- Do **not** introduce new node types or parallel graphs.
- Headless behavior and numbers (evals, stuck rates, LangSmith traces) must stay identical.

## Integration Path (Suggested Order)

1. Extract the queue-based owner thread behind an internal interface; keep the existing RLock implementation as the fallback / headless path during transition.
2. Add `persist=` and `observation_mode=` to the runner and CLI (default False for `--headed`).
3. Implement sidecar + latest-.state load logic for non-persist resume.
4. Wire headed runner/CLI to pass the observation flags.
5. Add unit tests for the command queue (using `MutableRamEmulator` or a fake that records commands) + integration under xvfb for headed smoke.
6. Measure: wall time between visible actions during boot + early game in headed vs before.
7. Once stable and tests green, flip the default implementation for `window != "null"` and delete the old branched code.
8. Update AGENTS.md / README only after the refactor lands.

## Why This Is More Optimal

- Eliminates most of the ad-hoc threading and duplication.
- Makes headed vs headless a *runtime profile* rather than a completely forked code path.
- Resume semantics become explicit and mode-appropriate.
- Easier to test, profile, and reason about (single owner of emulator state).
- Still satisfies "the game should not randomly pause due to any checkpointing or unnecessary noise" while the agent continues to play exactly as designed.

## References (Current Code)

- Live thread: `src/emulator/pyboy_wrapper.py` (`_live_loop`, `press_button`, `tick`)
- MemorySaver choice: `src/run/autonomous_runner.py` (`run()` headed branch)
- Tracing profile: `src/run/_langsmith.py` (`configure_tracing`)
- Compile support: `src/graph/graph.py:80` (`compile_graph`)
- Burst + guards: `autonomous_runner.py:160`, `nodes.py:205` (is_bootstrapping), supervisor
- Watch entry: `poke-runner --headed` / `src/run/autonomous_runner.py`
- Bootstrap ff: `src/emulator/bootstrap.py:170`
- Stuck / apply: `src/graph/nodes.py:266` (`apply_action_node`)

---

This note is intentionally non-prescriptive on exact class names. The goal is to record the direction so future work (or a full refactor) can pick it up cleanly without re-deriving the problem from scratch.

When implementing, run:
- `uv run pytest tests/ -q`
- Manual `uv run poke-runner --headed --max-steps 80` (headed smoke on real ROM)
- Headless regression: `uv run python -m src.run.cli --steps 200` + evals
