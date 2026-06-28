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
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(getInitialDemo());
  const [live, setLive] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);

  const loadDemo = (demo: AgentSnapshot) => {
    setLive(false);
    setSnapshot({ ...demo });
    setLastError(null);
  };

  const fetchState = useCallback(async (isLive: boolean) => {
    if (!isLive) return;
    try {
      const res = await fetch("/api/state", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AgentSnapshot = await res.json();
      // ensure minimal shape
      setSnapshot({
        ...getInitialDemo(),
        ...data,
        metrics: data.metrics || { steps: data.step || 0 },
      });
      setLastError(null);
      setPollCount((c) => c + 1);
    } catch (e: any) {
      setLastError(e.message || "fetch failed");
      // keep previous snapshot
    }
  }, []);

  // polling effect
  useEffect(() => {
    let timer: number | null = null;
    if (live) {
      fetchState(true);
      timer = window.setInterval(() => fetchState(true), POLL_MS);
    }
    return () => {
      if (timer) window.clearInterval(timer);
    };
  }, [live, fetchState]);

  const manualRefresh = () => {
    if (live) {
      fetchState(true);
    } else if (snapshot) {
      // re-apply current to trigger render
      setSnapshot({ ...snapshot });
    }
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
            title="Toggle live polling of /api/state"
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
