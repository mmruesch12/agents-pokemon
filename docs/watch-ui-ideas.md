# Watch / HUD UI Ideas (deferred)

Option 1 (richer terminal HUD) is **implemented**: after each `graph.invoke()` in
`AutonomousRunner.run()`, `log_intent_card()` emits a one-line card via `logger.info`.
See `format_intent_card()` / `log_intent_card()` in `src/run/autonomous_runner.py`. Use
`uv run poke-runner --headed -v` or `uv run poke-agent --headed -v` (or
`python -m src.run.autonomous_runner` / `python -m src.run.cli`) with normal
INFO logging to see cards during play.

The ideas below remain available for later implementation.

---

## 2. LangSmith traces (already built in)

```bash
uv run poke-runner --headed --langsmith --max-steps 120
```

Every graph step becomes a trace: supervisor → planner/navigator/battler → apply →
critic → memory, with LLM inputs/outputs when used.

**Pros:** Full decision history, no code changes.  
**Cons:** Browser tab, not overlaid on the game; latency between action and trace.

---

## 3. Companion overlay window (best “watch mode” UX)

A second window (tkinter, PyQt, or a small Dear ImGui panel) that updates after
each macro-step:

| Panel section | Source |
|---|---|
| Active specialist | `next_node` / routing |
| Current action | `last_action` + `last_action_result` |
| Goal | `active_subgoal`, `current_plan` |
| Status | `phase`, `stuck_count`, `critic_verdict` |
| Mini-map / position | `game_state.player` |

Hook it in one place — the loop in `autonomous_runner.run()` right after
`graph.invoke()`.

**Pros:** Clean separation from PyBoy/SDL threading; matches the live-thread
architecture.  
**Cons:** Two windows to arrange on screen.

---

## 4. Web dashboard (screenshot + state stream) — **implemented**

Shipped as React UI + FastAPI (`src/run/dashboard_server.py`, `dashboard/`).

```bash
cd dashboard && npm run build
uv run poke-agent dashboard --port 8765
```

- **`/api/state`** — agent snapshot JSON (demo or `data/watch/current.json`)
- **`/api/screenshot`** — PNG frame (demo or `data/watch/current.png`)

See [dashboard/README.md](../dashboard/README.md). Live snapshots are file-based; demo mode works ROM-free.

**Pros:** Nice layout, remote viewing, easy to extend (graphs, stuck meter).  
**Cons:** Polling/file I/O overhead in headed mode; WebSocket streaming remains a future enhancement.

---

## 5. Burn-in HUD on the game frame (true in-game overlay)

After each action (or on a timer in the live thread), composite text onto the
PyBoy framebuffer before SDL blit:

```
▶ RIGHT  →  (10,12)
Goal: Exit east
```

Using PIL on `pyboy.screen.image` — direction arrow, subgoal, stuck warning.

**Pros:** Single window, feels native.  
**Cons:** Touches the render path and lock; Game Boy resolution is tiny (160×144),
so text must be minimal; fights with dialog text on screen.

---

## 6. Directional “ghost” indicator (lightweight visual cue)

Instead of text, draw a semi-transparent arrow on the overlay showing
`last_action_result["direction"]` or pathfinding target. Even a terminal bell or
screen flash on replan (`critic_verdict == "replan"`) helps.

**Pros:** Readable at GB resolution.  
**Cons:** Still needs overlay plumbing (option 5 or companion canvas).

---

## 7. Sidecar file + static HTML viewer

Each step, write `data/watch_snapshot.json`:

```json
{
  "step": 42,
  "last_action": "navigate_right",
  "active_subgoal": "...",
  "screenshot_path": "data/frames/0042.png"
}
```

A self-contained `docs/watch.html` (like `product.html`) polls the JSON and shows
intent next to the latest frame.

**Pros:** No server process; easy to hack on.  
**Cons:** Polling lag; disk I/O unless you throttle writes.

---

## 8. Event bus (foundation for any of the above)

Add a tiny `ObservationBus` callback/listener in the runner:

```python
def on_step(state: AgentState, emu: PyBoyWrapper): ...
```

Nodes stay unchanged; the runner emits after each invoke. Any UI (terminal, web,
overlay) subscribes. Aligns with the “observation profile” direction in
`docs/future-headed-optimizations.md`.

**Pros:** One integration point, multiple UIs later.  
**Cons:** Small refactor before you see anything.

---

## What to show (high signal, low clutter)

For watching, these fields matter most:

1. **`last_action`** — `navigate_right`, `bootstrap_a`, `battle_fight`
2. **`active_subgoal`** — what the planner thinks it’s doing
3. **`phase`** — bootstrap / explore / battle
4. **`critic_verdict`** — proceed vs replan (explains sudden direction changes)
5. **`stuck_count`** — why it might replan soon
6. **`last_action_result`** — target coords, path length, battle phase

Bootstrap is special: repetitive `bootstrap_a` is intentional, so label it “intro
sequence” rather than “stuck.”

---

## Suggested path

| If you want… | Start with… |
|---|---|
| Something today, zero UI code | `poke-runner -v` + `--langsmith` |
| Best watch experience locally | Companion overlay window (#3) |
| Shareable / remote viewing | Web dashboard (#4) |
| Single-window feel | PIL burn-in HUD (#5), keep text minimal |
| Extensible foundation | Event bus (#8) → plug in any viewer |

The terminal intent card (option 1) is the lowest-effort high-impact baseline.
Companion window or web dashboard are the best long-term watch UX because Game Boy
resolution is brutal for in-frame text.