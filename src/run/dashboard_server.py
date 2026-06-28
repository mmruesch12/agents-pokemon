"""Minimal FastAPI server for the React agent dashboard.

Serves:
- built React UI (from dashboard/dist after `npm run build`)
- /api/state : current snapshot (demo or from data/watch/current.json)
- /api/screenshot : current PNG bytes
- static demo images

Designed for ROM-free demo use + live snapshots written by runner.
No control plane (non-goal).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.graph.state import initial_agent_state
from src.state.models import GameState

logger = logging.getLogger(__name__)

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIST = REPO_ROOT / "dashboard" / "dist"
DATA_WATCH = REPO_ROOT / "data" / "watch"
DEMO_SNAPSHOT_PATH = REPO_ROOT / "dashboard" / "public" / "demo-screenshot.png"
BOOT_SNAPSHOT_PATH = REPO_ROOT / "dashboard" / "public" / "demo-boot.png"

# In-memory latest (populated by snapshot emission or on load). Use None to force fresh demo.
_latest_snapshot: dict[str, Any] | None = None


def _load_snapshot_from_disk() -> dict[str, Any] | None:
    """Load latest compact snapshot written by runner if present."""
    json_path = DATA_WATCH / "current.json"
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text())
        # attach screenshot ref
        png_path = DATA_WATCH / "current.png"
        if png_path.exists():
            data.setdefault("screenshot_url", "/api/screenshot")
        return data
    except Exception as exc:
        logger.warning("Failed to load watch snapshot: %s", exc)
        return None


def _get_demo_snapshot() -> dict[str, Any]:
    """Return a representative snapshot containing both normal + issue indicators.

    This is the ROM-free entry point used by default and in tests.
    """
    # start from initial state and mutate to a rich example
    gs = GameState.model_validate({
        "player": {"map_group": 24, "map_id": 4, "map_name": "New Bark Town", "x": 8, "y": 12, "facing": 0, "money": 3000},
        "party": [{"species_id": 152, "species_name": "Chikorita", "level": 5, "hp": 20, "max_hp": 20}],
        "party_count": 1,
        "battle": {"in_battle": False, "phase": "none"},
    })
    state = initial_agent_state(gs)
    state.update({
        "metrics": {"steps": 42, "badges_earned": 0, "battles_won": 0},
        "last_action": "navigate_right",
        "last_action_result": {"direction": "right", "target": [12, 12], "path_length": 4},
        "active_subgoal": "Leave New Bark Town east",
        "current_plan": [
            "Current area: New Bark Town",
            "Explore New Bark Town",
            "Active subgoal: Leave New Bark Town east",
        ],
        "phase": "explore",
        "critic_verdict": "proceed",
        "critic_notes": "Action acceptable",
        "stuck_count": 1,
        "short_term_history": [
            "navigate:right@8,12",
            "navigate:down@8,13",
            "navigate:right@9,13",
        ],
        "next_node": "navigator",
    })

    snap = dict(state)
    snap["step"] = snap.get("metrics", {}).get("steps", 0)
    snap["screenshot_url"] = "/api/screenshot"  # will serve demo image
    snap["timestamp"] = "2026-06-28T10:00:00Z"
    return snap


def reset_demo_snapshot() -> None:
    """Test helper: clear any live override so next get returns a fresh demo."""
    global _latest_snapshot
    _latest_snapshot = None


def get_current_snapshot() -> dict[str, Any]:
    """Return the most recent snapshot (disk > in-memory override > fresh demo).

    When no disk override, we return a fresh demo to keep tests/launch deterministic.
    """
    global _latest_snapshot
    disk = _load_snapshot_from_disk()
    if disk is not None:
        disk = dict(disk)  # don't mutate the cached read
        disk.setdefault("source", "live_agent")
        return disk
    if _latest_snapshot is not None:
        return _latest_snapshot
    # Always return a fresh copy of the demo to avoid cross-test pollution
    return _get_demo_snapshot()


def set_current_snapshot(state: dict[str, Any]) -> None:
    """Called by snapshot writer / runner hook. Overrides until disk present."""
    global _latest_snapshot
    _latest_snapshot = dict(state)
    # ensure useful fields
    if "screenshot_url" not in _latest_snapshot:
        _latest_snapshot["screenshot_url"] = "/api/screenshot"


def update_from_agent_state(agent_state: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw AgentState (post graph.invoke) into a compact snapshot for UI."""
    snap: dict[str, Any] = {
        "metrics": agent_state.get("metrics", {}),
        "last_action": agent_state.get("last_action", ""),
        "last_action_result": agent_state.get("last_action_result", {}),
        "active_subgoal": agent_state.get("active_subgoal", ""),
        "current_plan": agent_state.get("current_plan", []),
        "subgoals": agent_state.get("subgoals", []),
        "phase": agent_state.get("phase", "explore"),
        "critic_verdict": agent_state.get("critic_verdict", "proceed"),
        "critic_notes": agent_state.get("critic_notes", ""),
        "stuck_count": agent_state.get("stuck_count", 0),
        "short_term_history": agent_state.get("short_term_history", []),
        "game_state": agent_state.get("game_state", {}),
        "next_node": agent_state.get("next_node", ""),
        "replan_count": agent_state.get("replan_count", 0),
        "error": agent_state.get("error", ""),
        "step": agent_state.get("metrics", {}).get("steps", 0),
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "screenshot_url": "/api/screenshot",
        "source": "live_agent",  # distinguishes from demo data in the UI
    }
    set_current_snapshot(snap)
    return snap


def emit_snapshot(agent_state: dict[str, Any], screenshot_bytes: bytes | None = None) -> Path:
    """Write current.json + current.png (if provided) for live dashboard consumption.
    Returns the written json path. Creates data/watch/ if needed.

    Uses atomic replace (write to .tmp then os.replace) so that readers (the
    dashboard polling /api/state) never see a partial file. This is important
    when a headed agent is actively emitting while the dashboard is open.
    """
    DATA_WATCH.mkdir(parents=True, exist_ok=True)
    snap = update_from_agent_state(agent_state)

    json_path = DATA_WATCH / "current.json"
    tmp_json = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_json.write_text(json.dumps(snap, indent=2))
    os.replace(tmp_json, json_path)

    if screenshot_bytes:
        png_path = DATA_WATCH / "current.png"
        tmp_png = png_path.with_suffix(png_path.suffix + ".tmp")
        tmp_png.write_bytes(screenshot_bytes)
        os.replace(tmp_png, png_path)

    return json_path



def create_app() -> FastAPI:
    app = FastAPI(title="Pokemon Gold Agent Dashboard")

    # IMPORTANT: register API routes BEFORE any static mount so /api/* always win
    @app.get("/api/state")
    async def api_state() -> JSONResponse:
        snap = get_current_snapshot()
        return JSONResponse(snap)

    @app.get("/api/screenshot")
    async def api_screenshot() -> Response:
        # prefer live watch png, fall back to demo pngs
        candidates = [
            DATA_WATCH / "current.png",
            DEMO_SNAPSHOT_PATH,
            BOOT_SNAPSHOT_PATH,
        ]
        for p in candidates:
            if p.exists():
                data = p.read_bytes()
                return Response(content=data, media_type="image/png")
        # last resort 1x1 transparent png
        tiny = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        return Response(content=tiny, media_type="image/png")

    @app.post("/api/snapshot")
    async def api_post_snapshot(payload: dict[str, Any]) -> JSONResponse:
        """Allow external tools/tests to push a snapshot (for verification)."""
        snap = update_from_agent_state(payload)
        return JSONResponse({"ok": True, "step": snap.get("step")})

    # Health for verification
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "has_dist": str(DASHBOARD_DIST.exists())}

    # Also expose demo explicitly
    @app.get("/api/demo/normal")
    async def demo_normal() -> JSONResponse:
        return JSONResponse(_get_demo_snapshot())

    # Serve built dashboard (static) *after* APIs. Use catch-all for SPA.
    def _safe_dist_file(requested: str) -> Path | None:
        """Return a safe Path under DASHBOARD_DIST or None if traversal/unsafe.

        Rejects: absolute paths, any ".." segment, paths that resolve outside dist.
        """
        if not requested:
            return DASHBOARD_DIST / "index.html"
        # Normalize: strip leading slashes
        cleaned = requested.lstrip("/")
        if not cleaned:
            return DASHBOARD_DIST / "index.html"
        # Reject obvious traversal early
        if ".." in cleaned.split("/"):
            return None
        # Build relative path only
        try:
            rel = Path(cleaned)
            if rel.is_absolute():
                return None
            candidate = (DASHBOARD_DIST / rel).resolve(strict=False)
            dist_resolved = DASHBOARD_DIST.resolve()
            # Must be inside or equal to dist
            try:
                candidate.relative_to(dist_resolved)
            except ValueError:
                return None
            if candidate.is_file():
                return candidate
        except Exception:
            return None
        return None

    if DASHBOARD_DIST.exists():
        # assets are under /assets/...
        app.mount("/assets", StaticFiles(directory=str(DASHBOARD_DIST / "assets")), name="assets")

        @app.get("/")
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str = ""):
            safe = _safe_dist_file(full_path)
            if safe is not None:
                return FileResponse(str(safe))
            # SPA fallback (or 404 for malicious paths)
            return FileResponse(str(DASHBOARD_DIST / "index.html"))
    else:
        # Fallback landing when no build yet (helps tests/dev)
        @app.get("/", response_class=HTMLResponse)
        async def _root_fallback() -> HTMLResponse:
            return HTMLResponse(
                "<html><body><h1>Agent Dashboard</h1>"
                "<p>Build the frontend: <code>cd dashboard && npm run build</code></p>"
                "<p>Then restart server. Demo API at <a href='/api/state'>/api/state</a></p>"
                "</body></html>"
            )

    return app


app = create_app()
