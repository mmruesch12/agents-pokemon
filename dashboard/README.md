# Agent Dashboard (React + FastAPI)

Live debug UI for watching agent state, screenshots, history, and stuck/replan alerts while the Pokemon Gold agent runs.

## Prerequisites

- Python deps: `uv sync` (installs `fastapi`, `uvicorn`)
- Frontend build (one-time or after UI changes):

```bash
cd dashboard && npm install && npm run build
```

The server serves static files from `dashboard/dist/`. Without a build, `/` shows build instructions.

## Launch

From the repo root:

```bash
uv run poke-agent dashboard --port 8765
# or: uv run python -m src.run.cli dashboard --host 127.0.0.1 --port 8765
```

Open [http://localhost:8765](http://localhost:8765).

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Built React UI (`dashboard/dist/index.html`) |
| `/api/state` | Current agent snapshot JSON (demo or live) |
| `/api/screenshot` | Current frame PNG |

Implementation: `src/run/dashboard_server.py`.

## Snapshot sources

**Demo (ROM-free):** On first request, the server synthesizes a representative snapshot from `initial_agent_state()` plus demo images in `dashboard/public/`. Works without a ROM or running agent — used by tests and local UI development.

**Live:** When the agent runs with snapshot emission enabled, the runner writes:

- `data/watch/current.json` — compact `AgentState` fields
- `data/watch/current.png` — latest screenshot

The dashboard prefers live files when present; otherwise it falls back to demo data.

## Development

Scripts from `package.json`:

```bash
cd dashboard
npm run dev          # Vite dev server (hot reload; API still needs poke-agent dashboard)
npm run build        # Production bundle → dist/
npm run test         # Vitest unit tests (src/App.test.tsx)
npm run lint         # Oxlint
npm run preview      # Preview production build locally
npx playwright test  # E2E (tests-e2e/; requires npm run build first)
```

## Related docs

- Main README dashboard section: [../README.md](../README.md)
- Watch UI alternatives: [../docs/watch-ui-ideas.md](../docs/watch-ui-ideas.md)
- Agent graph mental model: [../docs/agent-mental-model.html](../docs/agent-mental-model.html)