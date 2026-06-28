import { useCallback, useEffect, useState } from "react";
import type { AgentSnapshot } from "./lib/agentTypes";
import { getInitialDemo, allDemos } from "./lib/demoData";
import { ScreenshotPane } from "./components/ScreenshotPane";
import { StatusStrip } from "./components/StatusStrip";
import { ActionCard } from "./components/ActionCard";
import { SubgoalPanel } from "./components/SubgoalPanel";
import { PlayerPosition } from "./components/PlayerPosition";
import { MetricsStrip } from "./components/MetricsStrip";
import { HistoryLog } from "./components/HistoryLog";
import { IssueBanner } from "./components/IssueBanner";

import "./App.css";

const POLL_MS = 1500;

function App() {
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null);
  const [live, setLive] = useState(true); // default to tracking live agent sessions
  const [lastError, setLastError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);

  const loadDemo = (demo: AgentSnapshot) => {
    setLive(false);
    setSnapshot({ ...demo });
    setLastError(null);
  };

  // Always fetch the best available state from server (disk snapshot if running agent, else demo)
  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch("/api/state", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AgentSnapshot = await res.json();
      setSnapshot((prev) => ({
        ...(prev || getInitialDemo()),
        ...data,
        metrics: data.metrics || { steps: data.step || 0 },
      }));
      setLastError(null);
      setPollCount((c) => c + 1);
    } catch (e: any) {
      setLastError(e.message || "fetch failed");
      // keep whatever we have; only seed demo on very first error
      setSnapshot((prev) => prev || getInitialDemo());
    }
  }, []);

  // Polling only when live mode is enabled (for tracking a running agent)
  useEffect(() => {
    let timer: number | null = null;
    if (live) {
      fetchLatest();
      timer = window.setInterval(() => fetchLatest(), POLL_MS);
    }
    return () => {
      if (timer) window.clearInterval(timer);
    };
  }, [live]);  // fetchLatest is now stable (no deps)

  // Always attempt to load the current server state on first mount
  useEffect(() => {
    fetchLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const manualRefresh = () => {
    fetchLatest();
  };

  const toggleLive = () => {
    const next = !live;
    setLive(next);
    if (next) {
      setLastError(null);
    }
  };

  const current = snapshot;

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="brand">
          <span className="pokeball">◓</span>
          <h1>Pokémon Gold Agent Dashboard</h1>
          <span className="tag">debug + observe</span>
        </div>

        <div className="controls">
          <button
            className={`toggle ${live ? "on" : ""}`}
            onClick={toggleLive}
            title="Auto-poll /api/state to track a running agent (headed or not). Turn off to freeze view."
          >
            {live ? "LIVE ●" : "LIVE ○"}
          </button>
          <button className="btn" onClick={manualRefresh}>Refresh</button>

          <div className="demo-buttons">
            {allDemos.map((d, i) => (
              <button key={i} className="btn small" onClick={() => loadDemo(d.data)}>
                {d.label}
              </button>
            ))}
          </div>

          <div className="meta">
            {current?.metrics?.steps != null && <span>step {current.metrics.steps}</span>}
            {pollCount > 0 && live && <span className="poll">polls:{pollCount}</span>}
            {current?.source === "live_agent" && <span className="live-tag">LIVE (tracking agent)</span>}
            {lastError && <span className="err">err: {lastError}</span>}
          </div>
        </div>
      </header>

      <IssueBanner snapshot={current} />

      <div className="main-grid">
        <div className="left-col">
          <ScreenshotPane snapshot={current} onRefresh={manualRefresh} />
        </div>

        <div className="right-col">
          <StatusStrip snapshot={current} />

          <div className="row">
            <ActionCard snapshot={current} />
            <PlayerPosition snapshot={current} />
          </div>

          <SubgoalPanel snapshot={current} />

          <MetricsStrip snapshot={current} />
        </div>
      </div>

      <div className="bottom">
        <HistoryLog snapshot={current} />
      </div>

      <footer className="footer">
        <span>
          Signals: last_action • active_subgoal • critic_verdict • stuck_count • phase • short_term_history • game_state • metrics
        </span>
        <span className="hint">
          Use <code>uv run poke-agent dashboard</code> (or python -m src.run.cli dashboard). Real snapshots update via /api/state.
        </span>
      </footer>
    </div>
  );
}

export default App;
