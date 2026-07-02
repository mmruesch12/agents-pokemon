# Autonomous Agent Roadmap — Minimal Prescription, Strong Self-Correction

**Status (2026-06):** Active design doc. Phase 1 (feedback loop) is implemented or in progress; Phases 2–4 are planned.

**Goal:** The agent should progress with **quest-level knowledge** (subgoals, ROM event flags) and **generic policies** (dialog → interact, blocked move → try something else), not tile-by-tile walkthrough scripts. When stuck, it should **self-correct** via context-rich replanning, navigator arbitration, and episode memory — not new `(x, y)` special cases.

---

## North star

| Keep (low prescription) | Remove over time (high prescription) |
|-------------------------|--------------------------------------|
| Milestone subgoals (`"Choose a starter"`) | Tile targets (`STARTER_BALL_APPROACH = (5, 3)`) |
| ROM event flags (`has_starter`, `in_script`) | `LabPhase` state machine + `resolve_lab_pre_starter` |
| Generic policies (text box → interact) | Per-scene overrides (aide corridor, strict `path[0]` for exit) |
| Discovered landmarks | Hand-maintained `MAP_GRIDS` as primary nav source |

**Prescription budget:** Every merge should either reduce coordinate-level rules in `src/graph/phases/` or prove self-correction handled the case without them.

---

## Architecture (target state)

```
RAM parsers (flags, text box, script, party)
        ↓
Supervisor → Planner (subgoals from flags + LLM)
        ↓
Navigator (landmarks + A* + visit-aware + LLM arbitration)
Interactor (generic A/B when dialog or blocked)
        ↓
Critic (loop detect → replan) → Memory (landmarks, stuck episodes, facts)
        ↓
Retrieve on replan → Planner / Navigator
```

Phase modules (`house_exit`, `starter_quest`) become **milestone checkers** — `decompose_subgoals`, `is_satisfied`, `in_phase` — not routing engines.

---

## Phase 1 — Close the feedback loop

**Goal:** When stuck, LLM and memory drive recovery instead of more phase rules.

| ID | Work | Files | Status |
|----|------|-------|--------|
| **M3** | Inject `short_term_history`, critic notes, stuck count, failed direction, active subgoal into planner/navigator prompts; episode memory on replan / `stuck_count >= 2` | `src/graph/llm.py` | Done |
| **M11** | Navigator arbitration: at `stuck_count >= 2` or same-direction repeat at same tile, prefer LLM or visit-aware alternate over blind `path[0]` | `src/graph/nodes.py` | Done |
| **M4** | Visit-aware candidate ranking + anti-oscillation; expand walkable cardinals when loop detected | `src/graph/nodes.py` | Done |

**Success metric:** New Bark teacher-gate loop (`navigate:right` at `(9, 12)`) recovers without adding new coordinates. Tests in `tests/test_memory_highroi.py`.

**Env knobs:**

- `STUCK_ARBITRATION_THRESHOLD` (default `2`) — when navigator defers to LLM / visit-aware override
- `STUCK_THRESHOLD` (default `10`) — when supervisor forces replan

---

## Phase 2 — Generic interaction policy

**Goal:** Replace lab-specific interact routing with ROM-signal rules.

Collapse `needs_lab_interaction`, `lab_ball_picking_active`, `force_interactor`, etc. into:

1. `in_text_box` or `in_script` → interactor
2. Movement blocked and facing object/warp → interactor
3. `stuck_count >= N` on navigate at same tile → interactor, then replan

**Keep:** ROM gates (e.g. lab exit blocked until `EVENT_GOT_A_POKEMON_FROM_ELM`).

**Delete (behind eval):** `LabPhase` enum, `resolve_lab_pre_starter`, coordinate nav targets in `starter_quest.navigation_target()`.

**Success metric:** `--start-lab` still reaches New Bark in ≤ ~80 steps; `starter_quest.py` shrinks materially.

---

## Phase 3 — Spatial memory over static grids

**Goal:** Navigation targets from discovered landmarks, not hardcoded warps.

1. `navigation_target()` resolves via `known_landmarks` first; coordinates are fallback only.
2. `MAP_GRIDS` bootstrap walkability; movement outcomes update session grid.
3. Warp landmarks recorded automatically on `map_key` change in `memory_node`.

**Success metric:** Cold bedroom start discovers lab entrance without `NEW_BARK_LAB_WARP` in phase code.

---

## Phase 4 — Eval gates and metrics

Add to `src/eval/`:

| Metric | Measures |
|--------|----------|
| `stuck_events_per_milestone` | Self-correction quality |
| `replan_recovery_rate` | Replans that advance position or flag within N steps |
| `phase_coordinate_count` | Tactical prescription in `phases/*.py` (should trend down) |
| Milestone completion | Existing dataset milestones |

**Workflow for each stuck scenario:**

1. Reproduce in eval fixture (`MutableRamEmulator` or `@pytest.mark.rom`)
2. Fix with M3/M11/M4 first
3. Only if that fails, add minimal ROM-signal rule (not tile script)
4. Record via `capture_stuck_episode` in critic

---

## Deprecation ladder for phase modules

```
Level 3 (legacy):  Tile scripts + phase state machines
Level 2 (target):  Milestones + ROM flags + generic policies
Level 1 (stretch): Planner subgoals + landmark discovery only
```

Move down one level per milestone, gated by eval. Do not delete `house_exit` / `starter_quest` overnight — shrink them incrementally.

---

## Recommended execution order

```
Phase 1 (M3 → M11 → M4)   ← current
Phase 2 (generic interact)
Phase 3 (landmark-first nav)
Phase 4 (eval gates, ongoing)
```

Within memory work after Phase 1: **M5 + M7** (structured stuck facts on replan) → **M1** (cross-run summary retrieval). Defer FAISS/embeddings until scale warrants it.

See also: [memory-analysis.md](memory-analysis.md) for the full M0–M12 matrix.

---

## Relation to Elm's Lab fixes

The lab stuck-loop fixes (stall detector, party inference, pathfinding grid, `--start-lab` landmark seeding) were **Level 3 scaffolding** — necessary to prove the control plane works, but not aligned with the long-term goal.

Observability fixes (RAM flags, stuck-meter semantics) are **permanent**. Tile-level rules (`resolve_lab_pre_starter`, `ELMS_LAB_EXIT` strict path) are **candidates for Phase 2 removal** once Phase 1 self-correction passes eval gates.

---

## Useful commands

```bash
uv run pytest tests/test_memory_highroi.py -q   # Phase 1 regression
uv run pytest tests/ -q                          # full suite
uv run python -m src.run.cli --start-lab --steps 120
```