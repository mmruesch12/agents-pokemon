import React from "react";
import type { AgentSnapshot } from "../lib/agentTypes";
import { shortHistory } from "../lib/agentTypes";

interface Props {
  snapshot: AgentSnapshot | null;
}

export const HistoryLog: React.FC<Props> = ({ snapshot }) => {
  if (!snapshot) return null;
  const items = shortHistory(snapshot.short_term_history || [], 15);

  // simple loop detection for visual callout
  const seen = new Set<string>();
  const loopIndices: number[] = [];
  items.forEach((h, i) => {
    if (seen.has(h)) loopIndices.push(i);
    seen.add(h);
  });

  return (
    <div className="pane history-pane">
      <div className="pane-header">
        Recent History <span className="muted">(newest first, last 15)</span>
      </div>
      <div className="history-list">
        {items.length === 0 && <div className="history-empty">No history yet</div>}
        {items.map((entry, idx) => {
          const isLoop = loopIndices.includes(idx);
          return (
            <div key={idx} className={`history-item ${isLoop ? "loop" : ""}`}>
              {isLoop && <span className="loop-flag">LOOP</span>}
              {entry}
            </div>
          );
        })}
      </div>
      <div className="history-note">
        Loops and repetitive patterns trigger critic replan.
      </div>
    </div>
  );
};
