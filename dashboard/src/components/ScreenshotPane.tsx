import React from "react";
import type { AgentSnapshot } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
  onRefresh?: () => void;
}

export const ScreenshotPane: React.FC<Props> = ({ snapshot, onRefresh }) => {
  let url = snapshot?.screenshot_url || "/demo-screenshot.png";
  // Add cache buster so live updates (especially in headed sessions) reload the PNG
  // even when the URL path stays the same.
  const bust = snapshot?.timestamp ? new Date(snapshot.timestamp).getTime() : Date.now();
  url = url + (url.includes("?") ? "&" : "?") + "t=" + bust;

  const p = snapshot?.game_state?.player;

  return (
    <div className="pane screenshot-pane">
      <div className="pane-header">
        <span>Game Frame</span>
        {onRefresh && (
          <button className="small-btn" onClick={onRefresh} title="Refresh screenshot/state">
            ↻
          </button>
        )}
      </div>
      <div className="screenshot-wrap">
        <img
          src={url}
          alt="Current emulator screenshot"
          className="screenshot"
          onError={(e) => {
            (e.target as HTMLImageElement).src = "/demo-screenshot.png";
          }}
        />
        {p && (
          <div className="screenshot-overlay">
            <div>{p.map_name || "map"}</div>
            <div className="coords">
              ({p.x}, {p.y}) facing {p.facing}
            </div>
          </div>
        )}
      </div>
      <div className="pane-footer">
        {snapshot?.timestamp ? new Date(snapshot.timestamp).toLocaleTimeString() : "demo"}
      </div>
    </div>
  );
};
