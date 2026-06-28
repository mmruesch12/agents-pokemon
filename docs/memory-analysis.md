# Memory System Analysis

Assessment of how memory is implemented and used in the Pokemon Gold agent, and where it can be improved.

**Date:** 2026-06-28

---

## Executive summary

Memory in this repo is really **three layers**, and only two affect behavior today. The third (`LongTermMemory`) is mostly a write-only log.

| Layer | Utilization | Verdict |
|-------|-------------|---------|
| `memory_node` (milestones, maps) | High | Success — drives phases and progress |
| `short_term_history` + critic | Medium | Partial — loop detection works, context underfed to LLM |
| `stuck_count` | High | Success — replan routing and phase heuristics |
| LangGraph checkpoint (SQLite) | High (headless) | Success — true cross-session state on `--resume` |
| `visited_positions` | Low | Underused — eval metrics and LLM tile count only |
| `LongTermMemory` (JSON on disk) | Very low | Not utilized — write-only audit trail |
| `memory_retrievals` / `long_term_facts` | None | Dead fields on `AgentState` |

The architecture describes a ReAct loop (perceive → act → reflect → remember → retrieve), but **remember happens; retrieve does not.** The highest-leverage fix is wiring retrieval into LLM prompts on replan and navigate, using data already written to `data/memory/`.

---

## Architecture: three memory layers

### 1. In-graph memory (`memory_node`)

Runs every step after the critic: **critic → memory → supervisor**.

This node does **not** call `LongTermMemory`. It maintains session state:

| Field | What it does |
|-------|----------------|
| `maps_visited` | Appends current `map_key` on first visit |
| `milestones` | Detects events (house exit, rival battle, Route 29, badges, wild encounters) |
| `metrics.steps` | Increments step counter |
| Phase hooks | `house_exit.on_house_exit_complete()` / `starter_quest.on_starter_quest_complete()` on key milestones |

Phase modules (`house_exit`, `starter_quest`) use `maps_visited` for milestone logic — e.g. “left house” only counts if the player came from an indoor map.

**Verdict:** Genuinely utilized. Tests cover milestone detection (`test_memory_milestone_route_29`, graph integration tests).

Relevant code: `src/graph/nodes.py` (`memory_node`, `_check_milestone`).

### 2. Short-term memory (within a run)

Specialists append to `short_term_history` (last 20 entries), e.g. `navigate:right@5,8`.

**Consumers:**

- **Critic** — loop detection via recent repetition + `stuck_count`:
  - Same action 3× in last 5 history entries **and** `stuck_count >= 3`, **or**
  - `stuck_count >= STUCK_THRESHOLD` (default 10)
  - Sets `should_replan` and routes to planner on next supervisor tick

- **Navigator LLM** — only the *count* of `visited_positions`, not the history or tile list

- **`stuck_count`** (updated in `apply_action_node`) — also used by phase heuristics to switch navigate → interact indoors when stuck

**Verdict:** The critic → replan loop works but is narrow. History is not fed to planner, battler, or navigator beyond a single integer.

Relevant code: `src/graph/nodes.py` (`critic_node`, specialist history appends), `src/graph/llm.py` (`llm_navigate` prompt).

### 3. Long-term memory (`LongTermMemory`)

Class in `src/memory/long_term_memory.py`. Persists to `data/memory/facts.json` and `summaries.json`.

**Only `AutonomousRunner` uses it.**

| Method | When called | Used in decisions? |
|--------|-------------|-------------------|
| `add_fact()` | New milestone in runner loop | No |
| `summarize_history()` | Every 100 steps | No |
| `retrieve()` | Never in production | No |
| `build_faiss_index()` | Never | No |

**Verdict:** Write-only scaffolding. Keyword retrieval and optional FAISS exist but are not wired into the graph or LLM layer.

Relevant code: `src/run/autonomous_runner.py` (runner loop), `tests/test_memory.py` (isolated unit tests only).

### 4. LangGraph checkpoints (separate from JSON memory)

SQLite checkpointer (`data/checkpoints.sqlite`) persists full `AgentState` — including `short_term_history`, `milestones`, `maps_visited`, plans, stuck meter — across `--resume`.

**Verdict:** This is the real cross-session memory for headless runs. `LongTermMemory` JSON files are a parallel audit trail, not consulted on resume.

**Caveat:** Headed mode uses in-process `MemorySaver`, not SQLite. Session state may not survive process restarts the way headless `--resume` does.

Relevant code: `src/graph/graph.py` (`compile_graph`), `src/run/autonomous_runner.py` (resume logic).

---

## Field-by-field utilization

| Feature | Written? | Read for decisions? | Gap |
|---------|----------|---------------------|-----|
| `short_term_history` | Every action | Critic only (last 5) | Navigator/battler/planner never see recent actions |
| `visited_positions` | Every move (`update_game_state`) | LLM gets count only; evaluators | No tile-level “don’t revisit” or path bias |
| `maps_visited` | `memory_node` | Milestone + phase logic | Not passed to LLM prompts |
| `milestones` | `memory_node` + runner | Phase transitions, logging, eval | Not passed to planner on replan |
| `memory_retrievals` | Planner when LLM replans | **Never** | Misnamed — stores planner output, not retrievals |
| `long_term_facts` | Never | Never | Dead field on `AgentState` |
| `LongTermMemory` JSON | Runner | **`retrieve()` never called** | Facts/summaries not loaded on start or resume |

---

## What is working well

### Milestones and `maps_visited`

The most successful memory feature. Drives:

- `house_exit_complete` → unlocks starter quest phase
- `starter_quest_complete` on rival battle milestone
- Progress logging (Route 29, Cherrygrove, badges, wild encounters)

### `stuck_count` + critic replan loop

Failed moves increment stuck; successful moves and interactions decrement it. Phase modules use stuck count to prefer `interact_a` indoors. Critic escalates to replan when thresholds are hit. Supervisor routes to `planner_node` when `should_replan` is set.

### Checkpoints on resume (headless)

Full agent state restoration. Plans, history, and progress carry over between runs.

### Evaluators (read-only)

`visited_positions` and `milestones` feed `progress_per_steps`, `exploration_coverage`, and dataset eval in `src/eval/evaluators.py`. Useful for scoring runs, not for in-run decisions.

---

## What is not successfully utilized

### `LongTermMemory` retrieval loop

Facts and summaries are saved to disk but never loaded or injected into `llm_plan`, `llm_navigate`, or `llm_battle`. The agent cannot learn from past stuck episodes across runs via this layer.

### Planner context on replan

`llm_plan` receives map, party, badges, and battle flag — not milestones, stuck history, critic notes, or prior failed plans. Replanning is largely a fresh LLM call with thin context.

### `memory_retrievals` and `long_term_facts`

Schema placeholders. `memory_retrievals` is populated with `llm_plan` text but nothing reads it back. `long_term_facts` stays empty.

### `visited_positions` in navigation

Pathfinding uses a local A* `visited` set per search. Agent-level `visited_positions` is not used to penalize dead ends or break oscillation before the stuck threshold.

---

## Room for improvement (by impact)

### 1. Close the retrieval loop (highest impact)

Wire memory into LLM prompts:

- **On replan:** `retrieve(f"{map_name} {active_subgoal} stuck")` → inject top-k summaries into `llm_plan`
- **On navigate when stuck:** pass last 5 `short_term_history` entries + retrieved facts
- **On runner init / resume:** load `get_facts()` into `state["long_term_facts"]` and pass to planner

A single helper (e.g. `_memory_context(state, query) -> str` in `src/graph/llm.py`) would unify this.

### 2. Fix `memory_retrievals` semantics

Either actually retrieve and store there, or rename to `last_llm_plan` and stop treating it as memory. Current naming implies retrieval that does not happen.

### 3. Richer short-term context for the navigator

Give the LLM (and heuristics) more than a visited count:

- Last N actions on the current map
- Last direction that failed to move the player
- Critic verdict and notes when `should_replan` is set

### 4. Use `visited_positions` in navigation

Penalize directions toward already-tried dead ends. Break up/down oscillation before `STUCK_THRESHOLD`. Complements critic loop detection without extra LLM calls.

### 5. Summarize on stuck, not only every 100 steps

`summarize_history()` on a fixed timer produces generic logs. Triggering on `stuck_count >= threshold` or critic “replan” would capture failure context — exactly what retrieval should surface later.

### 6. Unify `memory_node` and `LongTermMemory`

Milestones are duplicated: graph state plus runner `add_fact()`. Either move persistence into `memory_node` (graph owns memory) or keep the runner as observer but always hydrate from disk on start. Avoid two sources of truth.

### 7. Structured facts

Facts like `milestone:Reached Route 29` are fine for logging. For decisions, structured entries help retrieval:

```json
{"type": "stuck", "map": "24:7", "pattern": "navigate:left", "resolution": "interact_a"}
```

Keyword `retrieve()` works better on intentional text than on raw `navigate:right@8,12; navigate:left@8,12` joins.

### 8. Real embeddings (lower priority)

`build_faiss_index()` uses random vectors — not useful for semantic search. Either integrate real embeddings (OpenRouter/OpenAI) or stay with keyword retrieval and structured facts. Half-implemented vector search adds complexity without benefit.

### 9. Battle and dialog memory

No memory of “already talked to Mom”, “chose starter”, etc. Event flags in `GameState` cover some state via RAM, but narrative context is not summarized for the LLM. A small fact table keyed by `map_key` + interaction would help indoor phases.

### 10. Tests and eval alignment

`test_memory.py` only tests `LongTermMemory` in isolation. Add integration tests that:

- Write a stuck summary → replan prompt includes it
- Resume loads facts into agent state

Eval datasets reference milestone strings that may not match graph emission exactly (e.g. `"Entered Elm's lab"` vs `"Reached Elm's Lab"`). Aligning names would make eval a better feedback loop.

---

## Recommended next step

Implement a minimal **retrieve → prompt** path:

1. On `should_replan` or `stuck_count >= threshold`, call `LongTermMemory.retrieve()` with a query built from `map_name`, `active_subgoal`, and recent history.
2. Inject results into `llm_plan` and, when stuck, into `llm_navigate`.
3. On runner start, hydrate `long_term_facts` from `facts.json`.
4. Add one integration test proving a stored summary appears in the planner prompt.

This closes the loop with small, focused changes and uses infrastructure that already exists.

---

## Key file references

| Path | Role |
|------|------|
| `src/graph/nodes.py` | `memory_node`, `critic_node`, history writes |
| `src/graph/llm.py` | LLM prompts (no memory injection today) |
| `src/graph/state.py` | `AgentState` memory fields |
| `src/memory/long_term_memory.py` | JSON persistence, keyword retrieve |
| `src/run/autonomous_runner.py` | `add_fact`, `summarize_history`, checkpoints |
| `src/eval/evaluators.py` | Read-only use of `visited_positions`, `milestones` |
| `tests/test_memory.py` | Unit tests for `LongTermMemory` only |