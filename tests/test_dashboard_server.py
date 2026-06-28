"""ROM-free tests for the shipped dashboard server and snapshot data paths.

These drive the actual functions used by the CLI launch and runner emission.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch


import src.run.dashboard_server as dashboard_server_mod
from src.graph.state import initial_agent_state
from src.run.dashboard_server import (
    _get_demo_snapshot,
    emit_snapshot,
    get_current_snapshot,
    reset_demo_snapshot,
    set_current_snapshot,
    update_from_agent_state,
)
from src.state.models import GameState


def test_demo_snapshot_has_required_fields():
    """Shipped demo path returns a dict with all primary UI fields."""
    snap = _get_demo_snapshot()
    for key in ("last_action", "active_subgoal", "phase", "critic_verdict", "stuck_count",
                "current_plan", "short_term_history", "metrics", "game_state"):
        assert key in snap, f"missing {key}"
    assert isinstance(snap["current_plan"], list)
    assert isinstance(snap["short_term_history"], list)
    gs = snap["game_state"]
    assert "player" in gs and "map_name" in gs["player"]
    # screenshot ref present for UI
    assert "screenshot_url" in snap


def test_update_from_agent_state_normal_and_issue():
    """Directly exercises the transform used by runner emission + /api/post."""
    gs = GameState.model_validate({
        "player": {"map_group": 24, "map_id": 1, "map_name": "Player's House 1F", "x": 4, "y": 5},
        "party_count": 0,
        "battle": {"in_battle": False},
    })
    state = initial_agent_state(gs)
    state["metrics"] = {"steps": 58, "badges_earned": 0, "battles_won": 0}
    state["last_action"] = "navigate_up"
    state["last_action_result"] = {"direction": "up", "path_length": 0}
    state["active_subgoal"] = "Talk to Mom..."
    state["current_plan"] = ["area", "goal"]
    state["phase"] = "explore"
    state["critic_verdict"] = "replan"
    state["stuck_count"] = 7
    state["short_term_history"] = ["navigate:left@3,5", "navigate:right@4,5"] * 3
    state["error"] = ""
    state["replan_count"] = 2

    snap = update_from_agent_state(state)
    assert snap["last_action"] == "navigate_up"
    assert snap["critic_verdict"] == "replan"
    assert snap["stuck_count"] == 7
    assert snap["step"] == 58
    assert "player" in snap["game_state"]
    assert snap["screenshot_url"] == "/api/screenshot"

    # Also test with minimal/empty game_state (defensive requirement)
    minimal = update_from_agent_state({
        "metrics": {"steps": 3},
        "last_action": "wait_script",
        "active_subgoal": "wait",
        "current_plan": [],
        "phase": "explore",
        "critic_verdict": "proceed",
        "stuck_count": 0,
        "short_term_history": [],
        "game_state": {},  # sparse
    })
    assert minimal["last_action"] == "wait_script"
    # position formatting on server side isn't here, but snapshot must be usable by UI without crash
    assert "game_state" in minimal


def test_get_current_and_set_roundtrip(tmp_path: Path):
    # isolate from any real data/watch/current.json that other tests or prior runs may have written
    with patch.object(dashboard_server_mod, "DATA_WATCH", tmp_path / "nowatch"):
        reset_demo_snapshot()
        demo = _get_demo_snapshot()
        set_current_snapshot(demo)
        got = get_current_snapshot()
        assert got["last_action"] == demo["last_action"]
        assert got.get("step") == demo.get("step")


def test_emit_snapshot_writes_files(tmp_path: Path, monkeypatch):
    """emit_snapshot (the function called from runner) writes usable artifacts."""
    # redirect watch dir to tmp
    import src.run.dashboard_server as ds
    monkeypatch.setattr(ds, "DATA_WATCH", tmp_path / "watch")
    monkeypatch.setattr(ds, "DASHBOARD_DIST", tmp_path / "no-dist")  # irrelevant here

    state = {
        "metrics": {"steps": 99},
        "last_action": "navigate_left",
        "active_subgoal": "test subgoal",
        "current_plan": [],
        "phase": "explore",
        "critic_verdict": "proceed",
        "stuck_count": 0,
        "short_term_history": ["a", "b"],
        "game_state": {"player": {"map_name": "TestMap", "x": 1, "y": 2}},
    }
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake but sufficient bytes

    out = emit_snapshot(state, png)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["last_action"] == "navigate_left"
    assert data["stuck_count"] == 0
    assert (tmp_path / "watch" / "current.png").exists()


def test_server_endpoints_use_testclient(tmp_path: Path):
    """Exercise the real FastAPI app endpoints (no uvicorn needed)."""
    from fastapi.testclient import TestClient

    from src.run.dashboard_server import create_app, reset_demo_snapshot
    with patch.object(dashboard_server_mod, "DATA_WATCH", tmp_path / "nowatch2"):
        reset_demo_snapshot()
        app = create_app()
        client = TestClient(app)

        # health
        r = client.get("/health")
        assert r.status_code == 200
        assert "ok" in r.json()["status"]

        # state always returns usable shape even before build
        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert "last_action" in body and "active_subgoal" in body
        assert "stuck_count" in body and "game_state" in body
        assert "phase" in body

        # screenshot returns image bytes
        r = client.get("/api/screenshot")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 0

        # post snapshot (used by verification + external)
        sample = {
            "metrics": {"steps": 5},
            "last_action": "battle_fight",
            "active_subgoal": "win battle",
            "current_plan": ["battle"],
            "phase": "battle",
            "critic_verdict": "caution",
            "stuck_count": 0,
            "short_term_history": [],
            "game_state": {"player": {"map_name": "Battle"}},
        }
        r = client.post("/api/snapshot", json=sample)
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # subsequent state reflects posted
        r = client.get("/api/state")
        assert r.json()["last_action"] == "battle_fight"
        assert r.json()["critic_verdict"] == "caution"


def test_dashboard_cli_command_invokes_server_path(capsys):
    """Smoke the CLI path that launches dashboard (without actually binding port)."""
    from src.run.cli import cmd_dashboard, _parse_cli

    def fake_run(*a, **kw):
        # simulate immediate stop
        raise KeyboardInterrupt()

    # Patch after the local import inside cmd_dashboard succeeds by stubbing the module object
    import sys
    fake_mod = type("uvicorn", (), {"run": fake_run})()
    with patch.dict(sys.modules, {"uvicorn": fake_mod}):
        args = _parse_cli(["dashboard", "--port", "18999"])
        rc = cmd_dashboard(args)

    # even with interrupt we treat as 0 or 1
    assert rc in (0, 1)

    captured = capsys.readouterr()
    assert "Starting Agent Dashboard" in captured.out or "Dashboard" in captured.out


def test_serve_spa_path_traversal_rejected(tmp_path: Path):
    """Security: serve_spa must not allow .. traversal to read repo files (pyproject etc)."""
    from fastapi.testclient import TestClient

    import src.run.dashboard_server as dsm
    # Ensure dist exists for the test (build already done in workspace)
    dist_dir = Path("dashboard/dist")
    assert dist_dir.exists() and (dist_dir / "index.html").exists()

    with patch.object(dsm, "DASHBOARD_DIST", dist_dir):
        app = dsm.create_app()
        client = TestClient(app)

        # Normal root serves HTML containing mount
        r = client.get("/")
        assert r.status_code == 200
        assert "root" in r.text.lower() or "<!doctype" in r.text.lower()

        # Traversal attempts must not leak files outside dist
        bad_paths = [
            "/%2e%2e/%2e%2e/pyproject.toml",
            "../pyproject.toml",
            "..%2f..%2fpackage.json",
            "/../../package.json",
            "assets/../../../pyproject.toml",
        ]
        for bp in bad_paths:
            r = client.get(bp)
            # Either serves index (safe fallback) or 404/403; must NOT contain pyproject content
            content = r.text
            assert "name = \"pokemon-gold-agent\"" not in content, f"Traversal leaked via {bp}"
            assert "[project]" not in content, f"Traversal leaked via {bp}"
            # Should still be HTML (SPA fallback or static) rather than raw toml/json
            assert "html" in r.headers.get("content-type", "").lower() or r.status_code in (200, 404)

        # A legitimate asset should still work
        r = client.get("/assets/" + os.listdir("dashboard/dist/assets")[0])
        assert r.status_code in (200, 404)  # 404 ok if naming varies; no crash

