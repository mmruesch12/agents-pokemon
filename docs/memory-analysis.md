# Memory System Analysis

Assessment of how memory is implemented and used in the Pokemon Gold agent, where it succeeds, where it falls short, and a consolidated plan for improvement.

**Date:** 2026-06-28  
**Revision:** 2 — adversarial review against current codebase (landmarks, hydration, exploration)

---

## Executive summary

Memory in this repo is **four behavioral layers**, not three. Two layers strongly affect navigation today; one is a partial retrieval loop; one is still write-only.

| Layer | Utilization | Verdict |
|-------|-------------|---------|
| `memory_node` (milestones, maps, landmark discovery) | **High** | Success — phase transitions, progress, spatial memory seeding |
| `known_landmarks` (in-run + `landmarks.json`) | **High** | Success — navigation targets, LLM prompts, cross-session hydrate |
| `short_term_history` + critic + `stuck_count` | **Medium** | Partial — loop detection works; history not fed to LLM |
| LangGraph checkpoint (SQLite, headless) | **High** | Success — full `AgentState` on `--resume` |
| `visited_positions` | **Medium** | Partial — frontier exploration + eval; not in navigator ranking |
| `LongTermMemory` summaries/facts (`retrieve()`) | **Very low** | Write-only — `facts.json` / `summaries.json` never read for decisions |
| `long_term_facts` (hydrated) | **Low** | Hydrated on start, **never passed to LLM** |
| `memory_retrievals` | **Low** | Write-only audit log (landmarks + planner text); never read |

**Revision 1 claimed:** “remember happens; retrieve does not.”  
**Revision 2 correction:** Landmark retrieval **does** happen (`retrieve_landmarks_from_state` → planner/navigator prompts and heuristic targets). **Summary/fact** retrieval (`LongTermMemory.retrieve()`) still does not.

The dominant same-run failure modes for stuck loops are not missing cross-run JSON — they are:

1. Replanning without `short_term_history`, `critic_notes`, or `stuck_count` in LLM prompts.
2. Navigator action selection: when A* returns a path, `path[0]` wins over the LLM even when landmarks and memory context were injected into `llm_navigate`.

---

## Adversarial review summary

Two independent reviews of revision 1 were run against the current tree (`src/memory/`, `src/graph/nodes.py`, `src/graph/llm.py`, `src/graph/exploration.py`, tests).

### Material errors in revision 1 (now corrected below)

| Claim in rev. 1 | Actual state |
|-----------------|--------------|
| `memory_node` does not call `LongTermMemory` | Calls `_persist_landmark_discoveries` → `add_landmark()` |
| Only `AutonomousRunner` uses `LongTermMemory` | `nodes.py` also uses it for landmark persistence |
| `LongTermMemory` is entirely write-only | Landmarks are read via `hydrate_state` and `retrieve_landmarks_from_state` |
| `long_term_facts` never written | Written by `hydrate_state()` on every run start |
| `visited_positions` used only for LLM count + eval | Also drives `exploration_target()` frontier search per map |
| `llm.py` has no memory injection | Landmark text injected into `llm_plan` and `llm_navigate` |
| Eval mismatch `"Reached Elm's Lab"` | Code emits `"Entered Elm's lab"` — matches `datasets.py` |

### Valid critiques retained

- Cross-run summary retrieval is still the biggest **unclosed** loop, but it is not the highest same-run ROI.
- `retrieve()` keyword miss falls back to `summaries[-k:]` — injecting that as “memory” can mislead the LLM.
- `memory_retrievals` is misnamed; planner **overwrites** landmark strings on LLM replan success.
- Navigator LLM is largely bypassed when a path exists — memory-rich navigator prompts have limited effect until arbitration changes.
- FAISS / embeddings remain dormant and low value at current scale.

---

## Architecture: four memory layers

### 1. In-graph memory (`memory_node`)

Runs every step: **critic → memory → supervisor**.

| Responsibility | Details |
|----------------|---------|
| `maps_visited` | First-visit tracking per `map_key` |
| `milestones` | House exit, starter quest, Route 29, badges, wild encounters |
| `metrics.steps` | Step counter |
| Phase hooks | `house_exit.on_house_exit_complete()`, `starter_quest.on_starter_quest_complete()` |
| **Landmark discovery** | First map visit, warp transitions (`last_map_transition`), Elm's lab entry, Mr. Pokemon's house |
| **Disk persist** | `_persist_landmark_discoveries` → `LongTermMemory.add_landmark()` |

Phase modules use `maps_visited` for milestone logic (e.g. house exit only when coming from indoor maps).

**Verdict:** Genuinely utilized. Tests: `test_memory_milestone_route_29`, `tests/test_landmarks.py`.

### 2. Landmark memory (`known_landmarks`)

Primary spatial memory added since revision 1.

| Component | Role |
|-----------|------|
| `src/memory/landmarks.py` | Discovery, merge, keyword retrieval, prompt formatting |
| `known_landmarks` on `AgentState` | In-run landmark store |
| `landmarks.json` | Cross-session persistence |
| `_attach_landmark_context()` | `retrieve_landmarks_from_state` → top 3 by query → `llm_plan` / `llm_navigate` |
| `gated_phase_target`, `_gate_starter_quest_target` | Navigation uses stored warp/door coords when known |
| `resolve_retired_geography()` | Post-starter route memory (east exit, route gates) |
| `hydrate_state()` | Merges checkpoint landmarks + disk on run start |
| `sync_landmarks_from_state()` | Runner syncs landmarks to disk each step |

**Verdict:** Highest-impact memory feature added recently. Closes part of the retrieval loop for **space**, not **episodes**.

### 3. Short-term memory (within a run)

| Field | Written | Read for decisions |
|-------|---------|-------------------|
| `short_term_history` | Every action (last 20) | Critic only (last 5) |
| `stuck_count` | `apply_action_node` | Critic, supervisor replan, phase interact fallbacks |
| `visited_positions` | `update_game_state` | `exploration_target` frontier; LLM gets count only |
| `last_map_transition` | `apply_action_node` on map change | `memory_node` warp landmark discovery |

**Critic replan triggers:**

- Same action 3× in last 5 history entries **and** `stuck_count >= 3`, **or**
- `stuck_count >= STUCK_THRESHOLD` (default 10)

**Verdict:** Stuck/replan loop works but planner/navigator/battler never see history or critic notes.

### 4. Episode memory (`LongTermMemory` summaries + facts)

| Method | When called | Used in decisions? |
|--------|-------------|-------------------|
| `add_landmark()` | `memory_node`, runner sync | **Yes** (via hydrate + retrieval) |
| `hydrate_state()` | Runner start | **Partial** (landmarks yes; facts hydrated but not prompted) |
| `add_fact()` | New milestone in runner | **No** |
| `summarize_history()` | Every 100 steps | **No** |
| `retrieve()` (summaries) | Never in production | **No** |
| `build_faiss_index()` | Never | **No** |

**Verdict:** Episode/summary layer is still write-only for decision-making.

### 5. LangGraph checkpoints (parallel persistence)

SQLite (`data/checkpoints.sqlite`) persists full `AgentState` for headless `--resume`. Headed mode uses in-process `MemorySaver` — weaker cross-restart continuity.

`hydrate_state()` runs after checkpoint load to merge disk landmarks/facts — bridges checkpoint and JSON when both exist.

---

## Field-by-field utilization (current)

| Feature | Written? | Read for decisions? | Gap |
|---------|----------|---------------------|-----|
| `known_landmarks` | `memory_node`, transitions | Navigation, LLM prompts, exploration gating | No negative memory (“tried A here, failed”) |
| `short_term_history` | Every action | Critic only | Not in LLM prompts |
| `visited_positions` | Every move | `exploration_target`, eval, LLM count | Not in navigator candidate ranking |
| `maps_visited` | `memory_node` | Milestones, phase logic | Not in LLM prompts |
| `milestones` | `memory_node` + runner | Phase transitions, eval | Not in `llm_plan` on replan |
| `long_term_facts` | `hydrate_state` | **Never** | One-line prompt fix unused |
| `memory_retrievals` | Landmarks + planner | **Never** | Overwritten by planner; audit only |
| `LongTermMemory.retrieve()` | N/A | **Never** | Summary loop still open |

---

## What is working well

### Milestones and `maps_visited`

Drives `house_exit_complete`, `starter_quest_complete`, progress logging, and eval scoring.

### Landmark discovery → navigation → LLM

Warp tiles (New Bark east exit, route gates, Elm's lab door, Mr. Pokemon entrance) are recorded on first discovery and reused for:

- `_navigation_target` / `gated_phase_target`
- `llm_plan` / `llm_navigate` landmark lines
- `resolve_retired_geography` after starter is chosen

### `stuck_count` + critic replan loop

Failed moves increment stuck; successes and interactions decrement. Phase modules escalate to `interact_a` when stuck indoors.

### Checkpoints + hydrate (headless)

Resume restores agent state; `hydrate_state` merges disk landmarks so spatial memory survives across threads/runs.

### Evaluators (read-only)

`visited_positions` and `milestones` feed progress and coverage metrics — useful for scoring, not in-run control.

---

## What is still underutilized

### Summary/fact retrieval loop

`facts.json` and `summaries.json` are written but `retrieve()` is never called outside tests. The agent cannot learn from past stuck episodes via summaries.

### Planner context on replan

`llm_plan` gets map, party, badges, battle, and landmarks — not `short_term_history`, `critic_notes`, `stuck_count`, `milestones`, or `long_term_facts`.

### Navigator arbitration vs memory

```375:394:src/graph/nodes.py
    llm_choice = llm_navigate(gs, state, candidates, relevant_landmarks, target=target)
    if door_exit:
        action = door_exit
    elif path:
        action = path[0]
    elif llm_choice and llm_choice in candidates:
        action = llm_choice
```

When A* finds a path, LLM choice (and its landmark context) is ignored. Memory injected into `llm_navigate` rarely changes the executed action.

### `memory_retrievals` semantics

Appends landmark strings during attach/discovery, then planner **replaces** the list with `[llm_plan]` on LLM success. Nothing reads the field for routing or prompts.

### Battler memory

`llm_battle` uses current HP only. Early-game battle routing is handled by supervisor + phase heuristics, not episode memory.

---

## Harmful interactions and risks

| Interaction | Risk |
|-------------|------|
| Landmark vs `path[0]` priority | LLM sees landmarks but cannot override a bad first path step |
| `retrieve()` fallback to `summaries[-k:]` | Irrelevant history injected as if relevant |
| `retrieve_landmarks_from_state` fallback to `landmarks[-k:]` | Arbitrary landmarks in prompt on query miss |
| Stale disk summaries + fresh checkpoint | Old stuck episode advice on a different map after resume |
| Visit penalties without warp awareness | Anti-oscillation could block legitimate door re-entry |
| Planner clears `memory_retrievals` | Loses landmark audit entries on heuristic replan |

---

## Improvement options matrix

Consolidated from revision 1 recommendations, adversarial review, and codebase comparison.  
**Effort:** S = hours, M = 1–2 days, L = multi-day.

| ID | Option | Effort | Impact | Dependencies | Risks | Status |
|----|--------|--------|--------|--------------|-------|--------|
| **M0** | Landmark discovery, retrieval, hydrate, nav gating | L | **High** — spatial memory across sessions | — | Landmark/path priority conflict | **done** |
| **M1** | Inject `LongTermMemory.retrieve()` summaries + `long_term_facts` into `llm_plan` / `llm_navigate` on replan or high stuck | M | Low–medium same-run; cross-run after many episodes | M5, M7 | Stale summaries mislead replans | **partial** — facts hydrated, not prompted |
| **M2** | Fix `memory_retrievals`: append-only log, rename, or store real retrievals; stop planner overwrite | S | None on nav; better telemetry | — | Refactor churn | **partial** — writes landmarks; planner clobbers |
| **M3** | Feed `short_term_history[-5:]`, `critic_notes`, `stuck_count`, last failed direction into planner + navigator prompts | S | **High** — stuck loops, indoor phases | — | Prompt noise | **todo** |
| **M4** | Use `visited_positions` in navigator candidate ranking / anti-oscillation | M | **Medium** — breaks oscillation before threshold | — | Warp/backtrack false positives | **partial** — `exploration_target` only |
| **M5** | Trigger `summarize_history()` on critic replan / stuck threshold, not only every 100 steps | S | Low same-run; enables M1 cross-run | — | Raw history joins are poor retrieval fuel | **todo** |
| **M6** | Unify persistence ownership (graph vs runner) | M | Low unless M1 ships | M1 | Two writers today; low harm while facts unread | **partial** — landmarks unified |
| **M7** | Structured stuck facts (`type`, `map`, `pattern`, `resolution`) | M | **Medium** for M1 quality | M5 | Schema maintenance | **todo** |
| **M8** | Real embeddings / FAISS for summaries | L | Negligible at current scale | API, cost | Complexity; random vectors useless today | **todo** (dormant) |
| **M9** | Battle/dialog narrative memory for LLM | M | **Low** early-game — phase heuristics dominate | — | Duplicates `starter_quest` / RAM flags | **partial** — heuristics, not LLM |
| **M10** | Integration tests: stuck summary → replan prompt; prompt wiring regression | S | Indirect — prevents regressions | M1, M3 | — | **partial** — `test_landmarks.py`, hydrate tests exist |
| **M11** | Navigator arbitration: when stuck, prefer LLM/heuristics over blind `path[0]` | M | **High** — unlocks landmark + memory prompts | M3 | Bad LLM override worsens movement | **todo** |
| **M12** | Rival-battle fast path (supervisor → battler/interactor) | S | **High** for rival milestone | Phase modules | Not a memory feature | **done** |

---

## Recommended execution order

Ranked for **reducing stuck loops** and **starter-quest progress**, not architectural completeness:

```
M3 → M11 → M4 → (M5 + M7) → M1
```

| Priority | Option | Rationale |
|----------|--------|-----------|
| 1 | **M3** | Replan is blind today — same-run context is cheapest highest ROI |
| 2 | **M11** | Without this, navigator LLM + landmark prompts are mostly wasted |
| 3 | **M4** | Extend existing `visited_positions` use; no extra LLM calls |
| 4 | **M5 + M7** | Better fuel before cross-run retrieval |
| 5 | **M1** | Close summary loop once structured stuck facts exist |

**Defer unless metrics prove need:** M8 (embeddings), M9 (battle narrative memory), M2 alone (rename without M3/M11), M6 without M1.

### Minimal shippable slice (one PR)

1. **M3:** Add `_prompt_context(state) -> str` in `llm.py` with history, critic, stuck.
2. **M11:** When `stuck_count >= 3`, prefer `llm_choice` over `path[0]` if valid.
3. **M1 (thin):** Append `long_term_facts[:5]` to `llm_plan` on replan (already hydrated).
4. **M10:** One test asserting replan prompt contains critic notes + a hydrated fact.

---

## Option details (reference)

### M3 — Rich short-term context (todo)

Give planner and navigator:

- Last 5 `short_term_history` entries
- `critic_notes`, `critic_verdict`, `stuck_count`
- Last action that did not change position

### M11 — Navigator arbitration (todo)

Today memory-rich `llm_navigate` calls are often no-ops. When stuck or repeating, allow LLM/heuristic override of `path[0]`.

### M4 — Visit-aware navigation (partial)

`exploration_target` already picks unvisited frontier tiles. Extend to navigator candidate scoring to break left/right oscillation earlier.

### M5 + M7 — Episode capture (todo)

Summarize on replan, not timer-only. Store structured stuck facts instead of raw `navigate:x@y` joins.

### M1 — Summary retrieval (partial)

`hydrate_state` already loads facts. Wire `retrieve()` + `long_term_facts` into replan prompts. Guard against `retrieve()` last-k fallback.

### M2 — `memory_retrievals` cleanup (partial)

Rename to `prompt_audit_log` or make append-only; never let planner wipe landmark entries.

### M8 — Embeddings (defer)

`build_faiss_index()` uses random vectors. Not worth enabling until summary volume justifies it.

### M9 — Dialog memory (defer)

Mom, starter ball, egg delivery handled by `GameState.raw_metadata` and `force_interactor`. LLM narrative memory is low ROI early game.

### M10 — Tests (partial)

Existing: `tests/test_memory.py`, `tests/test_landmarks.py` (hydrate, navigation, persistence).  
Missing: prompt-injection integration tests for M1/M3.

---

## Comparison to revision 1 recommendations

| Rev. 1 # | Topic | Rev. 2 status |
|----------|-------|---------------|
| 1 | Close retrieval loop | **Partial** — landmarks done; summaries/facts todo (M1) |
| 2 | Fix `memory_retrievals` | **Partial** (M2) |
| 3 | Rich short-term for navigator | **Todo** (M3) — still highest ROI |
| 4 | `visited_positions` in navigation | **Partial** (M4) — `exploration_target` exists |
| 5 | Summarize on stuck | **Todo** (M5) |
| 6 | Unify memory_node + LongTermMemory | **Partial** (M6) — landmarks unified |
| 7 | Structured facts | **Todo** (M7) |
| 8 | Real embeddings | **Defer** (M8) |
| 9 | Battle/dialog memory | **Defer** (M9) |
| 10 | Tests + eval alignment | **Partial** (M10); eval strings mostly aligned |
| — | *(new)* Navigator arbitration | **Todo** (M11) — critical gap found in review |
| — | *(new)* Landmark layer | **Done** (M0) |

---

## Key file references

| Path | Role |
|------|------|
| `src/graph/nodes.py` | `memory_node`, landmark discovery, `_attach_landmark_context`, navigator arbitration |
| `src/graph/llm.py` | LLM prompts; landmark injection; no history/fact injection yet |
| `src/memory/landmarks.py` | Discovery, retrieval, formatting, `landmarks.json` path |
| `src/memory/long_term_memory.py` | Facts, summaries, landmarks persistence, `hydrate_state` |
| `src/graph/exploration.py` | Frontier exploration via `visited_positions` |
| `src/graph/quest_geography.py` | Retired-phase geography from stored warp landmarks |
| `src/graph/state.py` | `known_landmarks`, `memory_retrievals`, `long_term_facts` |
| `src/run/autonomous_runner.py` | `hydrate_state`, `sync_landmarks`, `add_fact`, `summarize_history` |
| `src/eval/evaluators.py` | Read-only scoring |
| `tests/test_landmarks.py` | Landmark + hydrate + navigation integration |
| `tests/test_memory.py` | `LongTermMemory` unit + hydrate merge test |

---

## Bottom line

Revision 1 correctly identified an open retrieval loop but **understated progress on landmarks** and **overstated cross-run JSON retrieval as the highest-leverage fix**.

**Today:** Spatial memory (landmarks) is the success story — discovered in-graph, persisted to disk, hydrated on start, retrieved into prompts, and used for navigation gating.

**Still open:** Episode memory (stuck summaries, facts in prompts), short-term history in replan prompts, and navigator arbitration so LLM/memory context actually changes actions.

**Next:** Ship M3 + M11 + thin M1 as one focused PR; measure stuck frequency and starter-quest step count before investing in M8 or M9.