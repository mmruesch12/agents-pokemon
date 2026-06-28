# Proposal: Early-Game Progression — Elm's Lab, Starter Pokémon, Mr. Pokémon Quest, and First Rival Battle

Holistic design for extending the Pokemon Gold/Silver agent from **house-exit complete on New Bark Town (`24:4`)** through **starter acquisition**, **Route 29/30 travel**, **Mystery Egg + Pokedex delivery**, and **first trainer battle (rival on return to lab)** — reusing the established phase-module pattern without new parallel abstractions.

**Canon sources:** pret/pokegold disassembly (`constants/map_constants.asm`, `constants/event_flags.asm`, `maps/ElmsLab.asm`, `maps/NewBarkTown.asm`, `maps/MrPokemonsHouse.asm`, `maps/Route29.asm`), standard walkthrough sequence. **Follow-up observation required:** exact in-lab starter-ball tile coordinates and yes/no dialog timing should be confirmed on a live ROM dump (pret object events give starting points, not guaranteed pathfinding goals).

---

## 1. Game Sequence (Canon Mechanics)

The post-house early game is a **script-driven quest chain** gated by event flags, not free exploration. In order:

| Step | Location (`map_key`) | What happens | pret signals |
|------|---------------------|--------------|--------------|
| 1 | `24:4` New Bark Town | Walk north-west to lab entrance warp `(6,3)` → `24:5` | `warp_event 6,3 → ELMS_LAB` |
| 2 | `24:5` Elm's Lab | `ElmsLabMeetElmScene`: player auto-walks up; Elm intro dialog; `SCENE_ELMSLAB_CANT_LEAVE` blocks exit at `(4,6)/(5,6)` until starter chosen | `LabTryToLeaveScript`, `ElmText_Intro` |
| 3 | `24:5` | Interact with one of three Poke Balls `(6,3)/(7,3)/(8,3)` → yes/no → `givepoke` + `EVENT_GOT_*_FROM_ELM` + `EVENT_GOT_A_POKEMON_FROM_ELM` | `CyndaquilPokeBallScript` etc. |
| 4 | `24:5` | Post-choice: Elm directions, phone number; aide walks to player at `(4,8)/(5,8)` and gives **Potion** (`SCENE_ELMSLAB_AIDE_GIVES_POTION`) | `AideScript_GivePotion`, `verbosegiveitem POTION` |
| 5 | `24:4` | Exit lab; teacher at west edge `(1,8)/(1,9)` no longer blocks (requires `EVENT_GOT_A_POKEMON_FROM_ELM`) | `SCENE_NEWBARKTOWN_TEACHER_STOPS_YOU` |
| 6 | `24:3` Route 29 → `26:1` Route 30 → `26:10` Mr. Pokémon's House | Travel east/north; gate guard on Route 29 requires party Pokémon | Route gate scripts (party check) |
| 7 | `26:10` | Mr. Pokémon gives **Mystery Egg**; Oak appears, gives **Pokedex** | `EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON`, `EVENT_MR_POKEMONS_HOUSE_OAK` |
| 8 | Return `24:5` | Give egg to Elm → long dialog → rival theft cutscene setup | `EVENT_GAVE_MYSTERY_EGG_TO_ELM`, `EVENT_ELM_CALLED_ABOUT_STOLEN_POKEMON` |
| 9 | `24:5` | Rival battle (trainer battle) on return; officer scene may interleave | `battle.phase == TRAINER`, rival trainer event |

**Key pret map keys (group:map_id from WRAM):**

| Symbol | map_key | Notes |
|--------|---------|-------|
| `NEW_BARK_TOWN` | `24:4` | Lab warp `(6,3)` |
| `ELMS_LAB` | `24:5` | 5×6 indoor map |
| `ROUTE_29` | `24:3` | East exit from New Bark |
| `ROUTE_30` | `26:1` | North toward Cherrygrove |
| `MR_POKEMONS_HOUSE` | `26:10` | Egg + Oak |

**Key event flags (pret `event_flags.asm`; verify indices on ROM like existing Mom flag):**

| Symbol | Index (pret parse) | Role |
|--------|-------------------|------|
| `EVENT_GOT_A_POKEMON_FROM_ELM` | 26 | Master “has starter” flag |
| `EVENT_GOT_CYNDAQUIL_FROM_ELM` | 27 | Per-starter variant |
| `EVENT_GOT_TOTODILE_FROM_ELM` | 28 | Per-starter variant |
| `EVENT_GOT_CHIKORITA_FROM_ELM` | 29 | Per-starter variant |
| `EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON` | 30 | Egg quest complete |
| `EVENT_GAVE_MYSTERY_EGG_TO_ELM` | 31 | Returned to lab |
| `EVENT_RIVAL_NEW_BARK_TOWN` | 1040 | Rival sprite visibility (pre-battle) |
| `EVENT_MR_POKEMONS_HOUSE_OAK` | 1052 | Oak scene done |

Starter selection is **object interaction + yes/no dialog**, not a menu macro: face ball → `pokepic`/`cry` → `yesorno` → `givepoke`. The agent's existing `interactor_node` (A/B alternation) plus `needs_interaction()` / `needs_script_wait()` should carry this — no hardcoded button sequences.

---

## 2. Current Agent Gaps (Explicit Mapping)

| Game need | Current code | Gap |
|-----------|--------------|-----|
| Navigate to lab `24:5` | `house_exit.is_satisfied()` → `idle_node` emits `house_exit_done` | **Terminal idle blocks all post-house progress** |
| Lab map name / constants | `MAP_NAMES` in `gold_state_reader.py` | **No `ELMS_LAB` (`24:5`), `MR_POKEMONS_HOUSE` (`26:10`), `ROUTE_30` (`26:1`)** |
| Lab pathfinding | `MAP_GRIDS` in `pathfinding.py` | **No `24:5` grid**; `24:4` north row is coarse |
| Phase routing | Only `house_exit` in `phases/` | **No lab / egg-quest phase** |
| Navigation fallback | `_navigation_target()` → `(x+1, y)` | **Naive rightward drift**; fails lab interior and east-then-north routing |
| Subgoals | `initial_agent_state()` subgoals | Generic `"Visit lab or rival"` — **not flag-driven decomposition** |
| Objectives | `EARLY_GAME_OBJECTIVES` | **No `24:5` entry**; Route 29 objective exists but unreachable from idle |
| Planner | `house_exit.planner_allows_llm()` | LLM disabled only in house; **outdoors LLM never engaged post-idle** |
| Starter detection | `party_count`, `has_event_flag()` | **Reader never surfaces Elm flags** in `script_constants.py` |
| Milestones | `_check_milestone()` | **No** `"Chose first Pokemon"`, `"Reached Mr. Pokemon's house"`, `"First rival battle"` |
| Eval dataset | `eval/datasets.py` | Stale inputs (`map_group: 0,0`); **no lab/rival cases** |
| Battle | `battler_node` + `BattlePhase.TRAINER` | Exists generically; **no rival-specific milestone or forced routing when trainer battle starts mid-script** |
| Gate guard | — | **No party_count check** in navigation or phase guards |

**What already works (reuse, do not duplicate):**

- `needs_script_wait()` / `needs_interaction()` — Elm intro walk, aide walk-in, Oak cutscene
- `has_event_flag()` + `ByteArrayReader` test pattern (`tests/test_event_flags.py`)
- Phase module shape from `house_exit.py`: pure functions, graph stays thin
- `critic_node` stuck → replan; `memory_node` milestones + `maps_visited`
- `battler_node` with LLM + HP heuristic fallback

---

## 3. Holistic Extension (Single `early_game` Phase Chain)

**Principle:** Extend the phase pattern — **no new supervisor/critic/memory/apply_action abstractions**, no button macros, no WRAM hacks.

### 3.1 Phase composition

Replace the house-exit-only terminal with a **sequential early-game phase chain** registered from `phases/__init__.py` and delegated by `nodes.py` (same as `house_exit` today):

```
house_exit → starter_quest → (optional: open-world handoff)
```

For this scope, implement **`starter_quest`** as one phase module covering lab + egg quest + rival battle (internal sub-states driven by event flags, not separate graph nodes). Alternative: split `elm_lab.py` + `mr_pokemon_quest.py` — still the same pattern, no new routing layer.

Each phase exports the **same function surface** as `house_exit.py`:

| Function | Purpose for early-game |
|----------|------------------------|
| `in_phase(gs, state)` | True while quest incomplete |
| `is_satisfied(gs, state)` | True when rival battle entered or beaten (configurable terminal) |
| `force_interactor(gs, state)` | Lab: during Elm intro / ball yes-no / aide potion scene |
| `needs_extra_interaction(gs, state)` | Stuck indoors → prefer `interact_a` |
| `navigation_target(gs, state)` | Lab: Elm `(5,2)` then default ball tile; New Bark: lab warp `(6,3)`; Route 29: gate then north; Mr. Pokémon house warp |
| `door_exit_direction(gs)` | Lab exit warp at `(4,11)/(5,11)` → `down` when post-starter |
| `decompose_subgoals(gs)` | Flag-driven list (see §3.3) |
| `planner_allows_llm(gs, state)` | False in `24:5` (script-heavy); **True on `24:3`/`26:1`/`24:4` post-starter** |
| `on_map_change(...)` | Post-lab-warp settle ticks (mirror house stairs) |
| `milestone(gs, maps_visited, state)` | Emit target strings |
| `on_phase_complete(state, gs)` | Set `starter_quest_complete` (or similar) agent flag |

**Supervisor change (minimal):** After `house_exit.is_satisfied()`, route to **next active phase** instead of unconditional `idle`. `idle_node` becomes **generic terminal** when *all* registered phases satisfied — or rename to `hold_node`. Do **not** add parallel routing tables.

### 3.2 Event-flag-driven state machine (inside phase)

Sub-state derived from WRAM on every read — **no shadow quest state** except cheap agent flags for terminal satisfaction:

```
A: house_exit_complete ∧ ¬EVENT_GOT_A_POKEMON_FROM_ELM → go to lab, complete starter
B: EVENT_GOT_A_POKEMON_FROM_ELM ∧ ¬EVENT_GOT_MYSTERY_EGG → Route 29/30 → Mr. Pokémon
C: EVENT_GOT_MYSTERY_EGG ∧ ¬EVENT_GAVE_MYSTERY_EGG_TO_ELM → return to lab, interact Elm
D: EVENT_GAVE_MYSTERY_EGG_TO_ELM ∧ ¬in_rival_battle → trigger return scene / wait for battle
E: battle.in_battle ∧ battle.phase == TRAINER → satisfied when battle started (or when rival beaten)
```

Per-starter flags (`EVENT_GOT_CYNDAQUIL_FROM_ELM` etc.) refine milestone text but `EVENT_GOT_A_POKEMON_FROM_ELM` is the primary gate.

### 3.3 Subgoals and `state.py` updates

Update `initial_agent_state()` in `src/graph/state.py`:

```python
subgoals=[
    "Leave player house",
    "Visit Elm's lab",
    "Choose starter",
    "Deliver egg and battle rival",
    "Head toward Cherrygrove",
]
active_subgoal="Leave player house"
```

`decompose_subgoals()` delegation (extend `_decompose_subgoals` in `nodes.py`):

| Condition | Subgoals |
|-----------|----------|
| `24:4`, no starter | `["Enter Elm's lab", "Listen to Elm", "Choose a starter"]` |
| `24:5`, no starter | `["Talk to Elm", "Pick a Poke Ball", "Receive Potion from aide"]` |
| Has starter, not egg | `["Exit New Bark east", "Cross Route 29", "Visit Mr. Pokemon's house"]` |
| Has egg, not delivered | `["Return to New Bark", "Give Mystery Egg to Elm"]` |
| Post-delivery | `["Battle rival", "Heal if needed"]` |

### 3.4 `EARLY_GAME_OBJECTIVES` additions (`nodes.py`)

```python
"24:5": "Talk to Elm, choose a starter Pokemon, receive Potion",
"26:10": "Talk to Mr. Pokemon and receive the Mystery Egg from Oak",
```

Keep `24:4` as eastward exploration toward lab until starter flag set.

### 3.5 Reader and constants (`gold_state_reader.py`, `script_constants.py`)

Add to `script_constants.py` (pret-verified indices):

- `EVENT_GOT_A_POKEMON_FROM_ELM`, per-starter variants, egg flags, `EVENT_RIVAL_NEW_BARK_TOWN`
- Map constants: `MAP_ELMS_LAB = 5`, `MAP_MR_POKEMONS_HOUSE` (group 26, id 10)
- `MAP_KEY_ELMS_LAB = "24:5"`, `MAP_KEY_MR_POKEMONS_HOUSE = "26:10"`

Extend `read_script_state()` metadata:

- `has_starter: has_event_flag(EVENT_GOT_A_POKEMON_FROM_ELM)`
- `has_mystery_egg: has_event_flag(EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON)`
- `egg_delivered: has_event_flag(EVENT_GAVE_MYSTERY_EGG_TO_ELM)`

Add `MAP_NAMES` entries for lab, Route 30, Mr. Pokémon's House, Cherrygrove.

### 3.6 Pathfinding grids (`pathfinding.py`)

**Data-driven, not magic numbers in nodes:** derive blocked tiles from pret `ElmsLab.blk` / collision (script: capture via `scripts/diagnose_map_grid.py` pattern from house exit).

Minimum grids to add:

- **`24:5`**: desks, Elm at `(5,2)`, balls at `(6-8,3)`, warp at `(4-5,11)`, block `(4-5,6)` during cant-leave scene (phase can ignore blocked exit until starter flag)
- **`24:4`**: refine north path to `(6,3)` lab door; east path to Route 29 gate
- **`24:3`**, **`26:1`**, **`26:10`**: walkable corridors for A* (start coarse, refine from ROM)

Gate guard: if `party_count == 0` and map is Route 29 exit tile, `navigation_target` returns current position + `force_interactor` false — wait until starter (should not happen if flags correct).

### 3.7 Interaction and starter choice (no macros)

1. Pathfind to default ball tile — **configurable** `STARTER_BALL_TILE` env default `(7,3)` (Totodile middle ball); ROM probe can pick any ball since all three trigger full flow.
2. At ball tile: `navigation_target` returns current coords; `prefer_interact_candidate` true.
3. `interactor_node` A/B advances yes/no — on `SCRIPT_READ` with joypad unblocked, existing `needs_interaction()` handles it.
4. **Follow-up observation:** count typical dialog steps on live ROM; if yes/no stalls, add `needs_extra_interaction` when facing ball object (detect via position + map + ¬has_starter) — still not a button macro.

### 3.8 Battle and rival (`battler_node` unchanged structurally)

When `gs.battle.in_battle` and `gs.battle.phase == BattlePhase.TRAINER`:

- Supervisor already routes to `battler` — no change
- Milestone `"First rival battle"` when `in_battle` flips true with `party_count >= 1` and `EVENT_GAVE_MYSTERY_EGG_TO_ELM` or lab map context
- Heuristic fallback: `fight` (rival cannot run); optional low-HP `item` if Potion in inventory (read from `gs.inventory`)

### 3.9 Robustness

| Risk | Mitigation |
|------|------------|
| Script cutscenes block movement | Reuse `needs_script_wait()` — Elm walk-up, aide movement, Oak scene |
| Joypad blocked during animation | Existing `joypad_input_blocked()` mask |
| Dialog stalls | `needs_interaction()` + stuck interact fallback (port `stuck_interact_fallback` pattern from house) |
| False milestones | Require `maps_visited` includes prior maps (same fix as house exit) |
| LLM unavailable | Heuristic subgoals from flag machine; pathfinding primary direction; battler HP heuristic |
| Stuck at map edge | `critic_node` replan → planner refresh subgoals |
| Wrong lab coords | Grid from ROM capture; unit tests assert path exists from warp landing to ball tile |

**Explicit non-duplication:** Do not fork Mom-scene logic. Lab `force_interactor` only adds predicates on top of generic `needs_interaction()`.

---

## 4. Observable Outcomes and Verification

### 4.1 Milestones (emitted by `memory_node`)

| Milestone string | Condition |
|------------------|-----------|
| `"Entered Elm's lab"` | First visit `24:5` with `maps_visited` containing `24:4` |
| `"Chose first Pokemon"` | `party_count >= 1` ∧ `EVENT_GOT_A_POKEMON_FROM_ELM` |
| `"Reached Mr. Pokemon's house"` | First visit `26:10` |
| `"Delivered Mystery Egg to Elm"` | `EVENT_GAVE_MYSTERY_EGG_TO_ELM` |
| `"First rival battle"` | `battle.in_battle` ∧ `battle.phase == TRAINER` |

### 4.2 Unit tests (fake RAM, existing patterns)

Mirror `tests/test_house_exit_phase.py` and `tests/test_event_flags.py`:

**`tests/test_starter_quest_phase.py`** (new):

- `navigation_target` on `24:4` → lab warp coords
- `navigation_target` on `24:5` pre-starter → ball or Elm tile
- `is_satisfied` false before rival battle; true when synthetic `GameState` has trainer battle
- `decompose_subgoals` returns egg-quest strings when egg flag set in `ByteArrayReader` memory

**`tests/test_starter_milestones.py`** (new):

- Build RAM with `ADDR_PARTY_COUNT=1`, `EVENT_GOT_A_POKEMON_FROM_ELM` bit set → milestone `"Chose first Pokemon"`
- Battle mode trainer + `ADDR_BATTLE_MODE=2` → milestone `"First rival battle"`

**Extend `tests/test_early_progression.py`:**

- After house exit state, supervisor routes to navigator (not idle) when `starter_quest` active
- Navigator from New Bark `(13,6)` targets east/lab — not `house_exit_done`

### 4.3 Graph integration test

Extend pattern from `tests/test_house_exit_terminal.py`:

- 10 supervisor cycles with `house_exit_complete=True`, `map_key=24:4`, starter quest active → **non-zero** `navigate_*` (contrast with house terminal test)
- Synthetic satisfied starter quest → zero `navigate_*` (new terminal)

### 4.4 Optional ROM smoke (`@pytest.mark.rom`)

**`tests/test_rom_starter_quest.py`:**

- Resume from save state at New Bark post-house OR cold boot with high `run_max_steps`
- Assert `"Chose first Pokemon" in milestones` within N steps
- Separate longer test for egg quest if save-state fixture provided

### 4.5 Verification commands (concrete)

```bash
# Unit: phase helpers + milestones (no ROM)
uv run pytest tests/test_starter_quest_phase.py tests/test_starter_milestones.py tests/test_early_progression.py -q

# Regression: house exit still idles when starter quest not wired (during transition)
uv run pytest tests/test_house_exit_terminal.py tests/test_house_exit_phase.py -q

# Full suite
uv run pytest tests/ -q

# ROM smoke (user-supplied ROM in roms/)
uv run pytest tests/test_rom_starter_quest.py -m rom -v

# CLI capture evidence (post-implementation)
uv run python -m src.run.cli --steps 500 --thread-id starter-quest-v1 2>&1 | tee {SCRATCH}/cli-starter-quest.log
# Expect: milestones containing "Chose first Pokemon", final party_count>=1, map 24:5 or 24:4
```

### 4.6 Eval dataset updates (`eval/datasets.py`)

Add cases:

- `elms_lab_starter`: input `24:5`, `party_count=0` → expect subgoal containing "starter"
- `mr_pokemon_house`: input `26:10` → milestone `"Reached Mr. Pokemon's house"`
- `rival_battle`: input `in_battle=True`, `battle_mode=2`, `map 24:5` → phase `battle`

---

## 5. Implementation Order (When Building — Out of Scope for This Proposal)

1. **Constants + reader flags** — unlocks test RAM fixtures
2. **`starter_quest` phase module** — pure functions + tests
3. **Supervisor handoff** — house_exit satisfied → starter_quest (not idle)
4. **`MAP_GRIDS` for `24:5`, refine `24:4`** — ROM-validated
5. **Milestones + subgoals + EARLY_GAME_OBJECTIVES**
6. **Re-enable LLM planner outdoors** (`planner_allows_llm` true on routes)
7. **ROM smoke + CLI verification script** (`scripts/verify_starter_quest_state.py` mirroring house exit)

---

## 6. Non-Goals (This Phase)

- Progression past rival battle (Route 30 Joey, Cherrygrove mart, Violet Gym)
- Full menu navigation (bag, party swap mid-battle)
- Phone calls, day/night, Pokegear banking
- Auto-generation of all map grids from pret (manual + ROM probe is enough for now)
- Changes to PyBoy control plane, dashboard, or long-term memory architecture
- End-to-end autonomous demo in this proposal deliverable

---

## 7. Assumed Scope

- `src/state/gold_state_reader.py`, `src/state/script_constants.py`
- `src/graph/phases/` (new phase module alongside `house_exit.py`)
- `src/graph/nodes.py` (delegation + objectives + milestone dispatch)
- `src/graph/pathfinding.py`, `src/graph/state.py`, `src/graph/llm.py` (context only)
- `tests/test_house_exit_phase.py`, `tests/test_early_progression.py`, new starter tests
- `src/eval/datasets.py`
- Reference: `docs/house-exit-autonomy-analysis.md`

---

## 8. Risks and Follow-Up Observation

| Item | Notes |
|------|-------|
| Starter ball tile choice | pret places balls at `(6,3)`, `(7,3)`, `(8,3)`; any works. Confirm warp landing coords on live boot. |
| Yes/no dialog | Uses `yesorno` — B may mean "no"; interactor alternation should eventually answer yes. Monitor stuck meter. |
| Rival battle trigger | Occurs on return to lab after egg theft script — may need `post_warp_wait_steps` after map transitions |
| `EVENT_INITIALIZED_EVENTS` index | pret parser yields 54; codebase uses 53 (live-verified). New flags: verify with `tests/test_event_flags.py` pattern |
| Gate guard without Pokemon | Teacher/coord events on `24:4` west edge — agent must not leave east until `party_count >= 1` |

---

## 9. Relation to Full Autonomy

This proposal **keeps explicit phase scaffolding** but grounds completion in **pret event flags** and **generic script/battle routing** — the same two-layer model as house exit. As `GameState` enrichment and map grids improve, `starter_quest` should **shrink**: flag checks remain, coordinate hints become optional. Outdoors, re-enabling the LLM planner tests whether `_navigation_target` fallback `(x+1,y)` can be retired for Route segments.

**Bottom line:** One phase module, same supervisor flow, event-flag terminal — extends reproducible house exit to reproducible **starter + egg + rival battle** without parallel abstractions or button macros.