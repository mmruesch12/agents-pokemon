# House Exit Work: Scalability, Holism, and Path to Full Autonomy

Analysis of changes made to achieve reproducible cold-boot exit from the starting house in New Bark Town, and how that work relates to the long-term goal of an agent that plays without explicit per-section instructions.

---

## Summary of Changes

The work fell into four layers: **correct game-state perception**, **phase-aware routing**, **accurate navigation**, and **explicit goal completion**. Together they let the agent leave the starting house on cold boot without hardcoded button sequences or WRAM hacks.

### 1. WRAM and script-engine fixes (foundation)

Several WRAM addresses were wrong or misinterpreted. They were corrected against pret/pokegold:

| What | Fix |
|------|-----|
| `wEventFlags` | `0xD7B7` (was wrong offset) |
| `wScriptFlags` | `0xD15B` — script "running" is **bit 2**, not a boolean on `wScriptRunning` |
| `wJoypadDisable` | `0xD8BA` — only certain bits block input |
| Mom scene completion | `EVENT_PLAYERS_HOUSE_MOM_1` event flag |
| Map identity | `map_group:map_id` from WRAM directly; removed `loaded_map_key` shadow state |

`src/state/script_constants.py` centralizes pret constants (`SCRIPT_READ`, `SCRIPT_WAIT`, joypad masks, Mom entry position). `needs_script_wait()` and `needs_interaction()` now read the same signals the game uses — when scripts block movement vs. when A/B dialog is expected.

**Why this is holistic:** Every later decision (wait vs. interact vs. navigate) depends on reading the game correctly. Fixing perception at the WRAM layer fixes Mom dialog, post-stairs warp timing, and bootstrap — not just one symptom.

### 2. House-exit phase module (`src/graph/phases/house_exit.py`)

Indoor logic was consolidated into one phase module instead of scattered conditionals in nodes:

- **Routing:** `force_interactor()` during Mom scene; `navigation_target()` for stairs `(7,0)` on 2F and door `(6,7)` on 1F; `door_exit_direction()` → `navigate_down` at the warp tile
- **Guards:** `blocked_stairs_up()` blocks going back upstairs during Mom; `planner_allows_llm()` disables LLM planning indoors (deterministic heuristics)
- **Milestones:** `house_milestone()` requires visiting house maps before awarding `"Left house — New Bark Town"` — prevents false positives on synthetic `24:4` starts
- **Completion:** `on_house_exit_complete()` sets `house_exit_complete = True`; `is_satisfied()` checks that flag **and** `map_key == 24:4`

**Why this is scalable:** The pattern is reusable. Future phases (Elm's lab, Route 29) can follow the same shape: `navigation_target()`, `force_interactor()`, `is_satisfied()`, milestones. Graph nodes stay thin delegates; phase logic lives in testable pure functions.

### 3. Script-wait and interaction routing

The supervisor now branches on real script state:

```
bootstrap → [house_exit satisfied? → idle]
         → [script wait? → waiter]
         → [dialog / Mom? → interactor]
         → [force Mom? → interactor]
         → navigator / planner / …
```

`needs_script_wait()` handles `SCRIPT_WAIT_MOVEMENT`, `SCRIPT_WAIT`, and `SCRIPT_READ` with joypad blocked. `post_warp_wait_steps` (set when descending stairs into Mom at `(9,1)`) covers the brief period after map warp before scripts settle.

**Why this is holistic:** Mom dialog, stair warp, and door exit all use the same script-wait / interact machinery. No separate "Mom hack" path.

### 4. Pathfinding and map grids

`MAP_GRIDS` for `24:7`, `24:6`, and `24:4` were expanded with real obstacles: kitchen counter, Mom NPC, table, door warp tiles. Out-of-bounds tiles are blocked (no "infinite walkable" fallback).

**Why this is scalable:** Grids are data keyed by `map_key`. Adding a map means adding rows to `MAP_GRIDS` and optional phase targets — not rewriting navigation logic.

### 5. Terminal success state (structural fix, not a band-aid)

The main post-exit bug was the agent reaching New Bark Town, then spamming `navigate_right` at the map edge. The fix was architectural:

- New **`idle_node`** — emits `house_exit_done`, no joypad input
- **Supervisor** routes to `idle` when `house_exit.is_satisfied()`
- Removed post-exit subgoals, `suppress_post_exit_replan`, and `loaded_map_key` sync hacks

**Why this is holistic:** Success is a first-class graph state, not "stop navigating via special cases." The agent declares the house-exit goal done and idles. Future goals can add their own terminal nodes the same way.

### 6. Bootstrap hardening

`bootstrap.py` uses pret's `wScriptFlags` bit 2 for `map_script_active()`. Bootstrap reads `gs.player.map_group/map_id` from WRAM; `needs_bootstrap` treats `0:0` as uninitialized (not New Bark). Title-screen flow is driven by real game state, not a parallel map tracker.

### 7. Tests and verification (reproducibility)

| Layer | Coverage |
|-------|----------|
| Unit | `test_script_wait`, `test_event_flags`, `test_house_exit_phase`, `test_pathfinding` |
| Graph | `test_house_exit_terminal` — 10 cycles on satisfied `24:4` emit **zero** `navigate_*` |
| ROM integration | `test_rom_house_exit` — cold boot → milestone within 100 steps |
| Ops | `scripts/verify_house_exit_state.py`, `scripts/diagnose_mom_scene.py` |

169 tests pass; ROM test validates end-to-end on a real emulator.

**Why this is reproducible:** Each layer is tested independently. A WRAM regression fails unit tests; a routing regression fails terminal tests; a full-run regression fails the ROM test. Logs use `format_map_context()` (`24:7 Player's House 2F (3,4)`) for traceability.

### Reproducible exit path

```
24:7 bedroom  → pathfind to stairs (7,0) → warp to 24:6 at (9,1)
Mom scene     → interact_a while script waits / dialog active (~40 steps)
Post-Mom      → pathfind to door (6,7) → navigate_down → warp to 24:4 (13,5)
Milestone     → "Left house — New Bark Town" (~step 68)
Steps 69+     → house_exit_done (idle, no further navigation)
```

Verified: `Final: New Bark Town (24:4) at (13, 6)` on repeated CLI runs.

---

## Relation to the Ultimate Goal: Play Without Per-Section Instructions

**Short answer:** Yes, but only partly. This work builds the **general platform** the agent needs. The house exit itself is still **mostly explicit guidance** — the first full test of that platform, not proof the whole game runs autonomously yet.

### What moves toward full autonomy

These changes are **game-wide primitives**, not house-only hacks:

1. **Correct perception of the game engine** — script mode, joypad disable, event flags apply everywhere (gyms, rival battles, cutscenes, mart clerks).
2. **Semantic routing, not button macros** — supervisor routes by what the game is asking for (`wait` / `interact` / `navigate`), not replayed sequences.
3. **Reusable phase pattern** — `navigation_target`, `force_interactor`, `is_satisfied`, milestones; architecture scales, phases are optional scaffolding.
4. **General infrastructure** — grid pathfinding, LLM planner/navigator (present; disabled indoors for reliability), critic → memory → milestones, terminal goal states.

### What is still explicit

House exit still relies on hand-authored knowledge:

| Explicit piece | Example |
|----------------|---------|
| Phase module | Stairs at `(7,0)`, door at `(6,7)`, Mom at `(9,1)` |
| Map grids | Hand-drawn `24:6`, `24:7`, `24:4` obstacle layouts |
| Subgoals | `"Talk to Mom in the kitchen"`, `"Leave through front door"` |
| LLM disabled indoors | `planner_allows_llm()` returns `False` on house maps |
| Warp handling | `door_exit_direction()` → `navigate_down` at door tiles |
| Objectives dict | `EARLY_GAME_OBJECTIVES` per map key |

Today: **~80% scripted house logic on top of ~20% generic engine awareness.** That produced a reproducible win; it did **not** yet prove the agent can figure out Elm's lab or Route 29 with zero new phase code.

The default explorer outside phases is still naive — `_navigation_target()` falls back to `(x+1, y)` ("walk right").

### Two-layer mental model

```
┌─────────────────────────────────────────┐
│  Goal-specific hints (phases, grids)    │  ← house_exit today; Route 29 stub exists
├─────────────────────────────────────────┤
│  Generic control plane (WRAM, scripts,  │  ← main long-term value of this work
│  routing, pathfinding, LLM, memory)     │
└─────────────────────────────────────────┘
```

This work strengthens the bottom layer and proves the top layer can be small and testable when the bottom layer is correct.

### What "fully autonomous" would look like next

To need **fewer** explicit per-section instructions over time:

1. **Richer `GameState`** — warps, NPCs, interactable tiles from RAM (or vision), not hardcoded coords
2. **Event-flag–driven goals** — extend Mom-scene pattern to Elm, rival, badges
3. **Re-enable LLM planning** with better context (memory, flags, map graph); phases as fallbacks only
4. **Auto or semi-auto map graphs** — pret map data / collision instead of hand-drawn grids
5. **Hierarchical goals from memory** — e.g. "get starter from Elm" decomposed by planner, validated by critic + milestones

The house-exit phase would **shrink** (or disappear) as those primitives strengthen — same way `loaded_map_key` was removed once WRAM reading was fixed.

### Bottom line

| Question | Answer |
|----------|--------|
| Does this work toward the ultimate goal? | **Yes** — foundational perception and routing any autonomous run needs |
| Is the agent already fully autonomous per section? | **No** — house exit is largely explicit; first validated phase |
| Was this the right kind of work? | **Yes** — platform + reference phase beats one-off hacks; explicit parts are scaffolding |

**Suggested next step:** Re-enable the LLM planner outdoors first (New Bark → Route 29) while keeping phases as safety nets — tests whether the generic stack can carry more load without writing `phases/route_29.py` by hand.

---

## Key files

- `src/state/gold_state_reader.py` — WRAM parsing
- `src/state/script_constants.py` — pret script/event constants
- `src/graph/phases/house_exit.py` — house-exit phase
- `src/graph/nodes.py` — supervisor, idle, script-wait routing
- `src/graph/pathfinding.py` — map grids
- `tests/test_house_exit_terminal.py` — post-exit idle regression
- `tests/test_rom_house_exit.py` — cold-boot ROM integration

## Verification commands

```bash
uv run pytest tests/ -q
uv run pytest tests/test_rom_house_exit.py -m rom -v
uv run python -m src.run.cli --steps 80 --thread-id house-exit-v1
uv run python scripts/verify_house_exit_state.py
```