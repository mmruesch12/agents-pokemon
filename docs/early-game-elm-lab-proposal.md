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
| 5 | `24:4` | Exit lab; **teacher coord_event** at west edge `(1,8)/(1,9)` blocks leaving town without a Pokémon until `EVENT_GOT_A_POKEMON_FROM_ELM` (script pulls player back) | `SCENE_NEWBARKTOWN_TEACHER_STOPS_YOU`, `NewBarkTown_TeacherStopsYouScene1/2` |
| 6 | `24:3` Route 29 → `26:1` Route 30 → `26:10` Mr. Pokémon's House | Travel **east** from New Bark into Route 29, then north on Route 30 (open-world segment once teacher gate cleared) | `ROUTE_29` / `ROUTE_30` warps |
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

**Key event flags (pret `event_flags.asm`; story flags in main `const_def` block, sprite-visibility flags in `const_next 1600` “Johto people” section — verify on ROM via `tests/test_event_flags.py` pattern, same as `EVENT_PLAYERS_HOUSE_MOM_1 = 1735`):**

| Symbol | Index (pret `const_def` order) | Role |
|--------|-------------------------------|------|
| `EVENT_GOT_A_POKEMON_FROM_ELM` | 26 | Master “has starter” flag |
| `EVENT_GOT_CYNDAQUIL_FROM_ELM` | 27 | Per-starter variant |
| `EVENT_GOT_TOTODILE_FROM_ELM` | 28 | Per-starter variant |
| `EVENT_GOT_CHIKORITA_FROM_ELM` | 29 | Per-starter variant |
| `EVENT_GOT_MYSTERY_EGG_FROM_MR_POKEMON` | 30 | Egg quest complete |
| `EVENT_GAVE_MYSTERY_EGG_TO_ELM` | 31 | Returned to lab |
| `EVENT_RIVAL_NEW_BARK_TOWN` | 1725 | Rival sprite visibility at lab sign (`const_next 1600`) |
| `EVENT_MR_POKEMONS_HOUSE_OAK` | 1737 | Oak scene done at Mr. Pokémon's house (`const_next 1600`) |

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
| Teacher gate (`24:4` west edge) | — | **No check** for `party_count == 0` / `¬EVENT_GOT_A_POKEMON_FROM_ELM` before routing east toward Route 29 |

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

Add a second phase module alongside `house_exit.py` and wire it through the **existing delegation call sites** in `nodes.py` — the same pattern today:

```python
from src.graph.phases import house_exit  # nodes.py line 12
```

`phases/__init__.py` is currently a one-line package docstring only; there is **no registry**. Implementation adds `src/graph/phases/starter_quest.py` and `from src.graph.phases import house_exit, starter_quest` in `nodes.py`, then chains helpers at the same sites that already call `house_exit.*` (navigation, subgoals, milestones, interaction, map-change).

```
house_exit (complete) → starter_quest (active) → starter_quest.is_satisfied → idle
```

For this scope, **`starter_quest`** is one module covering lab + egg quest + rival battle (internal sub-states driven by event flags, not separate graph nodes). Alternative: split `elm_lab.py` + `mr_pokemon_quest.py` — still the same pattern, no new routing layer.

Each new phase mirrors the **actual exports** of `house_exit.py` (names below are the template — prefix/suffix follows house naming):

| `house_exit.py` export | `starter_quest.py` analogue | Purpose for early-game |
|------------------------|----------------------------|------------------------|
| `is_satisfied(gs, state)` | `is_satisfied(gs, state)` | True when rival battle entered (or beaten — configurable terminal) |
| `in_house_exit(gs, state)` | `in_starter_quest(gs, state)` | True while on lab/quest maps and quest incomplete |
| `mom_scene_pending(gs)` | `lab_scene_pending(gs)` | Elm intro / ball choice / aide potion script active |
| `needs_house_interaction(gs, state)` | `needs_lab_interaction(gs, state)` | Extra interact signals beyond generic `needs_interaction()` |
| `force_interactor(gs, state)` | `force_interactor(gs, state)` | Route to interactor during lab scenes |
| `navigation_target(gs, …)` | `navigation_target(gs, …)` | Lab warp `(6,3)` on `24:4`; ball tile on `24:5`; Route/MrP targets |
| `door_exit_direction(gs)` | `door_exit_direction(gs)` | Lab exit warp `(4,11)/(5,11)` → `down` when post-starter |
| `blocked_stairs_up(gs)` | `blocked_lab_exit(gs)` | Block premature lab exit at `(4,6)/(5,6)` until starter flag |
| `prefer_interact_candidate(gs)` | `prefer_interact_candidate(gs)` | Hold position + prefer `interact_a` during lab dialog |
| `stuck_interact_fallback(gs, state)` | `stuck_interact_fallback(gs, state)` | Stuck indoors → append `interact_a` candidate |
| `decompose_subgoals(gs)` | `decompose_subgoals(gs)` | Flag-driven list (see §3.3) |
| `planner_allows_llm(gs, state)` | `planner_allows_llm(gs, state)` | False in `24:5`; true on routes post-starter |
| `on_map_change(…)` | `on_map_change(…)` | Post-warp settle ticks after lab entry |
| `house_milestone(gs, maps_visited)` | `starter_milestone(gs, maps_visited)` | Emit target milestone strings |
| `on_house_exit_complete(state, gs)` | `on_starter_quest_complete(state, gs)` | Set `starter_quest_complete` agent flag |
| `format_map_context(gs)` | `format_map_context(gs)` | Optional log formatting |

**No changes to core supervisor/critic/memory/apply_action flow structure.** The existing graph order stays `bootstrap → [hold? → idle] → waiter → interactor → planner/navigator → critic → memory`. Today `supervisor_node` calls `house_exit.is_satisfied()` at the idle branch; extend by **swapping that predicate** for a thin delegator (e.g. `_hold_phase_satisfied(gs, state)`) that returns `starter_quest.is_satisfied()` once `house_exit_complete`, else `house_exit.is_satisfied()` — **one predicate at the existing call site**, no new branches, no `idle_node` rename. All other wiring is chained delegation in `_navigation_target`, `_decompose_subgoals`, `_check_milestone`, `needs_interaction`, `_navigation_candidates`, and `apply_action_node` — matching how `house_exit` is integrated today.

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

Teacher gate (`24:4`): while `party_count == 0` or `¬EVENT_GOT_A_POKEMON_FROM_ELM`, `navigation_target` on New Bark should **not** target the east Route 29 exit — prioritize lab warp `(6,3)` instead. If the player steps on `(1,8)/(1,9)`, existing `needs_script_wait()` / `needs_interaction()` handle the teacher pull-back script (no new macro).

### 3.7 Interaction and starter choice (no macros)

1. Pathfind to default ball tile — **configurable** `STARTER_BALL_TILE` env default `(7,3)` (Totodile middle ball); ROM probe can pick any ball since all three trigger full flow.
2. At ball tile: `navigation_target` returns current coords; `prefer_interact_candidate` true.
3. `interactor_node` A/B advances yes/no — on `SCRIPT_READ` with joypad unblocked, existing `needs_interaction()` handles it.
4. **Follow-up observation:** count typical dialog steps on live ROM; if yes/no stalls, extend `needs_lab_interaction()` (same role as `needs_house_interaction`) when facing a ball tile — still not a button macro.

### 3.8 Battle and rival (`battler_node` unchanged)

When `gs.battle.in_battle` and `gs.battle.phase == BattlePhase.TRAINER`:

- Existing `supervisor_node` battle branch routes to `battler` — unchanged
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

- When `house_exit_complete` and `¬starter_quest.is_satisfied()`, `_hold_phase_satisfied()` is false → navigator runs (not `house_exit_done`)
- Navigator from New Bark `(13,6)` targets lab warp — not naive `(x+1, y)` only

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
2. **`starter_quest` phase module** — pure functions mirroring `house_exit.py` exports + tests
3. **Delegation wiring in `nodes.py`** — chain `starter_quest.*` at existing call sites; extend hold predicate at existing `is_satisfied` call site
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
| Teacher gate without Pokemon | `coord_event (1,8)/(1,9)` on `24:4` (`NewBarkTown.asm`) — navigation must target lab before east exit until `EVENT_GOT_A_POKEMON_FROM_ELM` |

---

## 9. Relation to Full Autonomy

This proposal **keeps explicit phase scaffolding** but grounds completion in **pret event flags** and **generic script/battle routing** — the same two-layer model as house exit. As `GameState` enrichment and map grids improve, `starter_quest` should **shrink**: flag checks remain, coordinate hints become optional. Outdoors, re-enabling the LLM planner tests whether `_navigation_target` fallback `(x+1,y)` can be retired for Route segments.

**Bottom line:** One phase module, same graph node flow, event-flag terminal — extends reproducible house exit to reproducible **starter + egg + rival battle** via delegation at existing `nodes.py` call sites, without parallel abstractions or button macros.